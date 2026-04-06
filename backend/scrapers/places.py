"""
Core Google Maps scraping engine.

Uses a browser+HTTP hybrid approach:
- Camoufox (anti-detection Firefox) scrolls Google Maps to discover place links
- Parallel async httpx requests fetch individual place pages

Anti-detection: Camoufox fingerprinting, proxy rotation, behavioral mimicry,
hardened aria-label/text-based selectors, randomized delays.
"""
import asyncio
import random
import traceback
import urllib.parse
from time import time

import httpx

from .extract import extract_data, extract_possible_map_link
from backend.proxy import proxy_manager, get_random_ua
from backend.utils import extract_path, remove_nones
from backend import cache


class StuckInGmapsException(Exception):
    pass


class RetryException(Exception):
    pass


def unique_strings(lst):
    """Deduplicate a list while preserving order."""
    return list(dict.fromkeys(lst))


def create_search_link(query, lang, geo_coordinates, zoom):
    """Build a Google Maps search URL."""
    endpoint = urllib.parse.quote_plus(query)

    params = {"authuser": "0", "entry": "ttu"}
    if lang:
        params["hl"] = lang

    geo_str = ""
    if geo_coordinates:
        geo_coordinates = geo_coordinates.replace(" ", "")
        if zoom:
            geo_str = f"/@{geo_coordinates},{zoom}z"
        else:
            geo_str = f"/@{geo_coordinates}"

    url = f"https://www.google.com/maps/search/{endpoint}"
    if geo_str:
        url += geo_str
    url += f"?{urllib.parse.urlencode(params)}"
    return url


async def _human_delay(min_s=0.5, max_s=2.0):
    """Sleep for a random human-like interval."""
    await asyncio.sleep(random.uniform(min_s, max_s))


# --- Hardened JS selectors (text/aria-label based, not brittle CSS classes) ---

SPONSORED_LINKS_JS = """
() => {
    try {
        const results = [];
        const allLinks = document.querySelectorAll('[role="feed"] a[href*="/maps/place/"]');
        for (const a of allLinks) {
            const container = a.closest('[class]')?.parentElement;
            if (!container) continue;
            const text = container.innerText || '';
            if (/\\b(Sponsored|Ad|Ads)\\b/i.test(text)) {
                results.push(a.href);
            }
        }
        const sponsored = document.querySelectorAll('[aria-label*="Sponsored"], [aria-label*="sponsored"]');
        for (const el of sponsored) {
            const link = el.querySelector('a[href*="/maps/place/"]') || el.closest('a[href*="/maps/place/"]');
            if (link) results.push(link.href);
        }
        return [...new Set(results)];
    } catch (e) {
        return [];
    }
}
"""

END_OF_RESULTS_JS = """
() => {
    const body = document.body.innerText || '';
    if (/reached the end of the list/i.test(body)) return true;
    if (/no more results/i.test(body)) return true;
    const markers = document.querySelectorAll('p.fontBodyMedium > span > span');
    return markers.length > 0;
}
"""

SCROLL_FEED_JS = """
(selector) => {
    const feed = document.querySelector(selector);
    if (feed) feed.scrollTo(0, feed.scrollHeight);
}
"""

CAN_SCROLL_JS = """
(selector) => {
    const feed = document.querySelector(selector);
    if (!feed) return false;
    return feed.scrollHeight > feed.scrollTop + feed.clientHeight + 5;
}
"""

GET_LINKS_JS = """
(selector) => {
    const links = document.querySelectorAll(selector);
    return [...links].map(a => a.href).filter(h => h.includes('/maps/place/'));
}
"""


async def scrape_place(link, cookies, user_agent, proxy=None):
    """Fetch a single place page via async HTTP and extract structured data."""
    # Check cache first
    cached = cache.get(link)
    if cached:
        return cached

    proxy_url = proxy or (proxy_manager.get_proxy() if proxy_manager.enabled else None)

    async with httpx.AsyncClient(
        http2=True,
        proxy=proxy_url,
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        headers = {
            "User-Agent": user_agent or get_random_ua(),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookie_dict = {}
        if cookies:
            for c in cookies:
                cookie_dict[c["name"]] = c["value"]

        for attempt in range(5):
            try:
                resp = await client.get(link, headers=headers, cookies=cookie_dict)
                html = resp.text

                init_state = html.split(";window.APP_INITIALIZATION_STATE=")[1]
                app_state = init_state.split(";window.APP_FLAGS")[0]

                data = extract_data(app_state, link)
                data["is_spending_on_ads"] = False
                cache.put(link, data)
                return data

            except (IndexError, AttributeError):
                if attempt < 4:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise RetryException(f"Failed to extract data from {link} after 5 attempts")
            except Exception:
                if attempt < 4:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                traceback.print_exc()
                return None


def _extract_map_link_from_html(html):
    """Try to extract a single place link from search results HTML."""
    try:
        init_state = html.split(";window.APP_INITIALIZATION_STATE=")[1]
        app_state = init_state.split(";window.APP_FLAGS")[0]
        link = extract_possible_map_link(app_state)
        if link and extract_path(link).startswith("/maps/place"):
            return link
    except Exception:
        return None


async def scrape_places(data, progress_cb=None):
    """
    Main scraping entry point.

    Scrolls Google Maps search results using Camoufox (anti-detection Firefox),
    collects place links, then fetches each place page in parallel via httpx.

    Args:
        data: dict with query, max, lang, geo_coordinates, zoom, links
        progress_cb: optional async callback(found, scraped, elapsed)

    Returns:
        {"query": str, "places": list[dict]}
    """
    from camoufox.async_api import AsyncNewBrowser

    max_results = data["max"]
    query = data["query"]
    direct_links = data.get("links")
    start_time = time()

    proxy_url = proxy_manager.get_proxy() if proxy_manager.enabled else None

    async with AsyncNewBrowser(
        headless=True,
        proxy={"server": proxy_url} if proxy_url else None,
    ) as browser:
        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        # Navigate to Google Maps search
        search_link = create_search_link(
            query, data["lang"], data["geo_coordinates"], data["zoom"]
        )
        await page.goto(search_link, wait_until="domcontentloaded", timeout=30000)

        # Handle cookie consent
        try:
            consent_btn = page.get_by_role("button", name="Accept all")
            await consent_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass  # No consent dialog

        # Check for blocking
        if "/sorry/" in page.url:
            raise Exception("Detected by Google, retrying...")

        # Collect place links
        if direct_links:
            discovered_links = direct_links
        else:
            discovered_links = await _scroll_and_collect(page, max_results, start_time)

        # Get sponsored links before closing
        sponsored = await page.evaluate(SPONSORED_LINKS_JS) if not direct_links else []

        # Grab cookies + UA for HTTP fetching
        cookies = await context.cookies()
        user_agent = await page.evaluate("() => navigator.userAgent")

        await context.close()

    # --- Fetch each place page in parallel via httpx ---
    if not discovered_links:
        return {"query": query, "places": []}

    discovered_links = unique_strings(discovered_links)

    sem = asyncio.Semaphore(5)
    scraped_count = 0

    async def fetch_one(link):
        nonlocal scraped_count
        async with sem:
            result = await scrape_place(link, cookies, user_agent)
            scraped_count += 1
            if progress_cb:
                await progress_cb(len(discovered_links), scraped_count, time() - start_time)
            return result

    tasks = [fetch_one(link) for link in discovered_links]
    results = await asyncio.gather(*tasks)
    places = remove_nones(results)

    for p in places:
        p["query"] = query

    # Mark sponsored
    for place in places:
        place["is_spending_on_ads"] = place.get("link", "") in sponsored

    return {"query": query, "places": places}


async def _scroll_and_collect(page, max_results, start_time):
    """Scroll the Google Maps results feed and collect place links."""
    WAIT_TIME = 40 + random.uniform(-5, 10)
    links = []

    try:
        await page.wait_for_selector('[role="feed"]', timeout=15000)
    except Exception:
        # No feed — might be single result or no results
        if "/maps/search/" in page.url:
            html = await page.content()
            link = _extract_map_link_from_html(html)
            return [link] if link else []
        elif "/maps/place/" in page.url:
            return [page.url]
        return []

    scroll_start = time()

    while True:
        # Scroll to bottom of feed
        await page.evaluate(SCROLL_FEED_JS, '[role="feed"]')
        await _human_delay(0.3, 1.5)

        # Extract place links
        current_links = await page.evaluate(GET_LINKS_JS, '[role="feed"] > div > div > a')
        links = unique_strings(current_links)

        if max_results and len(links) >= max_results:
            return links[:max_results]

        # Check if we've reached the end
        is_end = await page.evaluate(END_OF_RESULTS_JS)
        if is_end:
            return links

        # Timeout — stuck scrolling
        elapsed = time() - scroll_start
        if elapsed > WAIT_TIME:
            print("Google Maps stuck scrolling. Retrying after a minute.")
            await asyncio.sleep(random.uniform(55, 70))
            raise StuckInGmapsException()

        # Reset timeout if scroll position changed
        can_scroll = await page.evaluate(CAN_SCROLL_JS, '[role="feed"]')
        if can_scroll:
            scroll_start = time()
        else:
            await _human_delay(0.1, 0.4)

    return links
