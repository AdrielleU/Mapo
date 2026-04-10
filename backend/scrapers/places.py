"""
Core Google Maps scraping engine.

Uses a browser+HTTP hybrid approach:
- Camoufox (anti-detection Firefox) scrolls Google Maps to discover place links
- Parallel async httpx requests fetch individual place pages

Anti-detection: Camoufox fingerprinting, proxy rotation, behavioral mimicry,
hardened aria-label/text-based selectors, randomized delays.
"""
import asyncio
import html as htmlmod
import json
import math
import random
import re
import traceback
import urllib.parse
from time import time

import httpx

from .extract import extract_data, extract_possible_map_link
from backend.proxy import proxy_manager, get_random_ua
from backend.utils import extract_path, remove_nones
from backend import cache
from backend.config import config


class StuckInGmapsException(Exception):
    pass


class RetryException(Exception):
    pass


def unique_strings(lst):
    """Deduplicate a list while preserving order."""
    return list(dict.fromkeys(lst))


def _split_app_state(page_html):
    """Extract the APP_INITIALIZATION_STATE JSON string from a Maps HTML page."""
    init_state = page_html.split(";window.APP_INITIALIZATION_STATE=")[1]
    return init_state.split(";window.APP_FLAGS")[0]


def radius_to_zoom(radius_meters: float, latitude: float = 0.0) -> float:
    """Convert a search radius in meters to a Google Maps zoom level.

    Uses the Web Mercator formula. Clamped to range [1, 21].
    """
    if radius_meters <= 0:
        return config.scraping.default_zoom
    lat_rad = math.radians(latitude)
    zoom = math.log2(156543.0 * math.cos(lat_rad) / (radius_meters / 256.0))
    return max(1.0, min(21.0, round(zoom, 1)))


def create_search_link(query, lang, geo_coordinates, zoom, radius_meters=None):
    """Build a Google Maps search URL.

    If *radius_meters* is provided and geo_coordinates are set, the radius
    is converted to a zoom level which overrides the *zoom* parameter.
    """
    endpoint = urllib.parse.quote_plus(query)

    params = {"authuser": "0", "entry": "ttu"}
    if lang:
        params["hl"] = lang

    # Convert radius to zoom if provided
    if radius_meters and geo_coordinates:
        try:
            lat = float(geo_coordinates.replace(" ", "").split(",")[0])
            zoom = radius_to_zoom(radius_meters, lat)
        except (ValueError, IndexError):
            pass

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


async def _human_delay(min_s=None, max_s=None):
    """Sleep for a random human-like interval."""
    min_s = min_s if min_s is not None else config.scraping.min_delay
    max_s = max_s if max_s is not None else config.scraping.max_delay
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
                page_html = resp.text
                data = None

                # Strategy 1: fetch from /maps/preview/place endpoint (full data)
                preview_match = re.search(r'(/maps/preview/place\?[^"]+)', page_html)
                if preview_match:
                    try:
                        preview_path = htmlmod.unescape(preview_match.group(1))
                        preview_url = "https://www.google.com" + preview_path
                        resp2 = await client.get(preview_url, headers=headers, cookies=cookie_dict)
                        raw = resp2.text
                        if raw.startswith(")]}'"):
                            raw = raw[5:]
                        data = extract_data(raw, link)
                    except Exception:
                        data = None  # fall through to next strategy

                # Strategy 2: parse APP_INITIALIZATION_STATE (old format)
                if data is None and ";window.APP_INITIALIZATION_STATE=" in page_html:
                    try:
                        data = extract_data(_split_app_state(page_html), link)
                    except Exception:
                        data = None

                # Strategy 3: extract minimal data from [3][5] embedded string
                if data is None and ";window.APP_INITIALIZATION_STATE=" in page_html:
                    try:
                        data = _extract_minimal_from_init_state(page_html, link)
                    except Exception:
                        data = None

                if data is not None:
                    data["is_spending_on_ads"] = False
                    cache.put(link, data)
                    return data

                # No strategy worked on this attempt
                if attempt < 4:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

                print(f"[Mapo] Skipping place (no data after 5 attempts): {link[:80]}")
                return None

            except Exception:
                if attempt < 4:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                traceback.print_exc()
                return None


def _extract_minimal_from_init_state(page_html, link):
    """Extract minimal place data from APP_INITIALIZATION_STATE [3][5].

    Google now lazy-loads detailed data, but [3][5] still contains:
    name, coordinates, place_id. Returns a dict with whatever is available.
    """
    parsed = json.loads(_split_app_state(page_html))

    raw = parsed[3][5]
    prefix = ")]}'"
    if raw.startswith(prefix):
        raw = raw[len(prefix) + 1:]

    inner = _json.loads(raw)
    place = inner[0] if inner else None
    if not place or not isinstance(place, list):
        return None

    # Extract what's available
    data = {
        "place_id": place[14][0][4] if len(place) > 14 and place[14] else None,
        "name": place[1] if len(place) > 1 else None,
        "description": None,
        "main_category": None,
        "categories": [],
        "rating": None,
        "reviews": 0,
        "price_range": None,
        "status": "operational",
        "phone": None,
        "phone_international": None,
        "website": None,
        "address": None,
        "detailed_address": {},
        "coordinates": f"{place[3][2]},{place[3][3]}" if len(place) > 3 and place[3] and place[3][2] else None,
        "link": link,
        "is_spending_on_ads": False,
        "is_temporarily_closed": False,
        "is_permanently_closed": False,
    }

    if not data["name"]:
        return None

    return data


def _extract_map_link_from_html(html):
    """Try to extract a single place link from search results HTML."""
    try:
        link = extract_possible_map_link(_split_app_state(html))
        if link and extract_path(link).startswith("/maps/place"):
            return link
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Browser launchers (pluggable backends)
# ---------------------------------------------------------------------------

async def _launch_camoufox(proxy_url):
    """Launch Camoufox (anti-detection Firefox) via AsyncCamoufox context manager."""
    from camoufox.async_api import AsyncCamoufox

    kwargs = {"headless": config.scraping.headless}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    # AsyncCamoufox returns a BrowserContext directly
    ctx_manager = AsyncCamoufox(**kwargs)
    context = await ctx_manager.__aenter__()
    page = await context.new_page()
    # Store the context manager so we can __aexit__ it in cleanup
    return page, context, ctx_manager, None


async def _launch_patchright(proxy_url):
    """Launch Patchright (anti-detection Chromium)."""
    from patchright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=config.scraping.headless,
        proxy={"server": proxy_url} if proxy_url else None,
    )
    context = await browser.new_context(
        locale="en-US",
        timezone_id="America/New_York",
        user_agent=get_random_ua(),
    )
    page = await context.new_page()
    return page, context, pw, browser


async def scrape_places(data, progress_cb=None):
    """
    Main scraping entry point.

    Scrolls Google Maps search results using a stealth browser (CloverLabs
    Camoufox or Patchright), collects place links, then fetches each place
    page in parallel via httpx.

    Args:
        data: dict with query, max, lang, geo_coordinates, zoom, links
        progress_cb: optional async callback(found, scraped, elapsed)

    Returns:
        {"query": str, "places": list[dict]}
    """
    max_results = data["max"]
    query = data["query"]
    direct_links = data.get("links")
    start_time = time()

    proxy_url = proxy_manager.get_proxy() if proxy_manager.enabled else None

    browser_type = config.scraping.browser

    if browser_type == "patchright":
        page, context, _pw, _browser = await _launch_patchright(proxy_url)
    else:
        page, context, _pw, _browser = await _launch_camoufox(proxy_url)

    try:

        # Navigate to Google Maps search
        search_link = create_search_link(
            query, data["lang"], data["geo_coordinates"], data["zoom"],
            radius_meters=data.get("radius_meters"),
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

    finally:
        # Clean up browser resources
        # For Camoufox: _pw is the AsyncCamoufox context manager, _browser is None
        # For Patchright: _pw is the Playwright instance, _browser is the Browser
        if _pw and hasattr(_pw, '__aexit__'):
            try:
                await _pw.__aexit__(None, None, None)
            except Exception:
                pass
        else:
            try:
                await context.close()
            except Exception:
                pass
            if _browser:
                try:
                    await _browser.close()
                except Exception:
                    pass
            if _pw:
                try:
                    await _pw.stop()
                except Exception:
                    pass

    # --- Fetch each place page in parallel via httpx ---
    if not discovered_links:
        return {"query": query, "places": []}

    discovered_links = unique_strings(discovered_links)

    sem = asyncio.Semaphore(config.scraping.concurrency)
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
    WAIT_TIME = config.scraping.scroll_timeout + random.uniform(-5, 10)
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
