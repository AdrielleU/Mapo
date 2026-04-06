"""
Core Google Maps scraping engine.

Uses a browser+HTTP hybrid approach:
- Headless Chrome scrolls Google Maps to discover place links
- Parallel HTTP requests fetch individual place pages (much faster)

Anti-detection features:
- Proxy rotation support
- Hardened selectors (aria-label/role-based, text-content fallbacks)
- Behavioral mimicry (randomized scroll delays, timing jitter)
- User-agent rotation
"""
import random
import traceback
import urllib.parse
from time import sleep, time

from botasaurus import bt, cl
from botasaurus.browser import Driver, browser, AsyncQueueResult, Wait, DetachedElementException
from botasaurus.cache import DontCache
from botasaurus.request import request

from .extract import extract_data, extract_possible_map_link
from backend.proxy import proxy_manager, get_random_ua


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


def perform_visit(driver, link):
    """Navigate to a Google Maps URL, handling cookie consent on first visit."""
    if driver.config.is_new:
        driver.google_get(link, accept_google_cookies=True)
    else:
        driver.get_via_this_page(link)


def _retry_on_error(func, error_types, retries=3, wait_time=None, on_exhausted=None):
    """Retry a function on specific exception types."""
    for attempt in range(retries):
        try:
            return func()
        except tuple(error_types) as e:
            if attempt < retries - 1:
                traceback.print_exc()
                print("Retrying")
                if wait_time:
                    sleep(wait_time)
            else:
                if on_exhausted:
                    on_exhausted(e)
                raise


def _human_delay(min_s=0.5, max_s=2.0):
    """Sleep for a random human-like interval."""
    sleep(random.uniform(min_s, max_s))


def _get_lang(data):
    return data["lang"]


def _get_proxy(data):
    """Get proxy for Botasaurus decorators."""
    return proxy_manager.get_proxy()


# --- Hardened sponsored link detection ---
# Uses text-content heuristic instead of brittle CSS classes.
SPONSORED_LINKS_JS = """
function get_sponsored_links() {
    try {
        const results = [];
        // Strategy 1: Find elements with "Sponsored" or "Ad" text
        const allElements = document.querySelectorAll('[role="feed"] a[href*="/maps/place/"]');
        for (const a of allElements) {
            const parent = a.closest('[class]');
            if (!parent) continue;
            // Walk up to find any sibling/child with ad indicator text
            const container = parent.parentElement;
            if (!container) continue;
            const text = container.innerText || '';
            if (/\\b(Sponsored|Ad|Ads)\\b/i.test(text)) {
                results.push(a.href);
            }
        }
        // Strategy 2: Fallback — look for aria-label containing "Sponsored"
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
return get_sponsored_links();
"""

# Hardened end-of-results detection JS
END_OF_RESULTS_JS = """
function check_end_of_list() {
    // Strategy 1: Look for "You've reached the end of the list" text
    const body = document.body.innerText || '';
    if (/reached the end of the list/i.test(body)) return true;
    if (/no more results/i.test(body)) return true;
    // Strategy 2: Check for the end-marker span (fallback)
    const markers = document.querySelectorAll('p.fontBodyMedium > span > span');
    return markers.length > 0;
}
return check_end_of_list();
"""


@request(
    close_on_crash=True,
    output=None,
    parallel=5,
    async_queue=True,
    max_retry=5,
    retry_wait=5,
)
def scrape_place(requests, link, metadata):
    """Fetch a single place page via HTTP and extract data."""
    cookies = metadata["cookies"]
    os_name = metadata["os"]
    user_agent = metadata.get("user_agent") or get_random_ua()

    html = requests.get(
        link,
        cookies=cookies,
        browser="chrome",
        os=os_name,
        user_agent=user_agent,
        timeout=12,
    ).text

    try:
        init_state = html.split(";window.APP_INITIALIZATION_STATE=")[1]
        app_state = init_state.split(";window.APP_FLAGS")[0]
    except (IndexError, AttributeError):
        raise RetryException("Failed to find APP_INITIALIZATION_STATE, retrying...")

    data = extract_data(app_state, link)
    data["is_spending_on_ads"] = False
    return data


def _extract_map_link_from_html(html):
    """Try to extract a single place link from search results HTML."""
    try:
        init_state = html.split(";window.APP_INITIALIZATION_STATE=")[1]
        app_state = init_state.split(";window.APP_FLAGS")[0]
        link = extract_possible_map_link(app_state)
        if link and cl.extract_path_from_link(link).startswith("/maps/place"):
            return link
    except Exception:
        return None


@browser(
    lang=_get_lang,
    close_on_crash=True,
    max_retry=3,
    reuse_driver=True,
    headless=True,
    output=None,
)
def scrape_places(driver: Driver, data):
    """
    Main scraping entry point. Scrolls Google Maps search results in a headless
    browser, collects place links, and dispatches them to scrape_place() via
    an async queue for parallel HTTP fetching.
    """
    max_results = data["max"]
    query = data["query"]

    place_queue: AsyncQueueResult = scrape_place()

    sponsored_links = None

    def get_sponsored_links():
        nonlocal sponsored_links
        if sponsored_links is None:
            sponsored_links = driver.run_js(SPONSORED_LINKS_JS)
        return sponsored_links

    def scroll_and_collect():
        """Scroll the results feed and push discovered links to the queue."""
        start_time = time()
        base_wait = 40
        WAIT_TIME = base_wait + random.uniform(-5, 10)  # Jittered timeout

        meta = {
            "cookies": driver.get_cookies_dict(),
            "os": bt.get_os(),
            "user_agent": driver.user_agent,
        }

        # Direct link mode: skip scrolling
        if data["links"]:
            place_queue.put(data["links"], metadata=meta)
            return

        while True:
            feed = driver.select('[role="feed"]', Wait.LONG)

            if feed is None:
                # Single result or no results
                if driver.is_in_page("/maps/search/"):
                    link = _extract_map_link_from_html(driver.page_html)
                    if link:
                        place_queue.put([link], metadata=meta)
                elif driver.is_in_page("/maps/place/"):
                    place_queue.put([driver.current_url], metadata=meta)
                return

            feed.scroll_to_bottom()
            _human_delay(0.3, 1.5)  # Behavioral mimicry

            # Extract links — use ARIA-based selector, filter for Maps place URLs
            raw_links = driver.get_all_links(
                '[role="feed"] > div > div > a', wait=Wait.LONG
            )
            # Filter to only Google Maps place links
            place_links = [l for l in raw_links if "/maps/place/" in l]

            if max_results is None:
                links = place_links
            else:
                links = unique_strings(place_links)[:max_results]

            place_queue.put(links, metadata=meta)

            if max_results is not None and len(links) >= max_results:
                return

            # Hardened end-of-results check via JS (text-content based)
            is_end = driver.run_js(END_OF_RESULTS_JS)
            if is_end:
                return

            elapsed = time() - start_time
            if elapsed > WAIT_TIME:
                print("Google Maps stuck scrolling. Retrying after a minute.")
                sleep(random.uniform(55, 70))  # Jittered retry wait
                raise StuckInGmapsException()

            if driver.can_scroll_further('[role="feed"]'):
                start_time = time()
            else:
                _human_delay(0.1, 0.4)

    search_link = create_search_link(
        query, data["lang"], data["geo_coordinates"], data["zoom"]
    )
    perform_visit(driver, search_link)

    if driver.is_in_page("/sorry/"):
        raise Exception("Detected by Google, retrying...")

    failed_to_scroll = False

    def on_exhausted(e):
        nonlocal failed_to_scroll
        failed_to_scroll = True
        print("Failed to scroll after retries. Skipping.")

    try:
        _retry_on_error(
            scroll_and_collect,
            [DetachedElementException],
            retries=5,
            on_exhausted=on_exhausted,
        )
        if driver.config.is_retry:
            print("Successfully scrolled to the end.")
    except StuckInGmapsException as e:
        if driver.config.is_last_retry:
            on_exhausted(e)
        else:
            raise

    places = place_queue.get()
    places = bt.remove_nones(places)

    for p in places:
        p["query"] = query

    ad_links = [] if data["links"] else get_sponsored_links()
    for place in places:
        place["is_spending_on_ads"] = place["link"] in ad_links

    result = {"query": query, "places": places}

    if failed_to_scroll or any(p is None for p in places):
        return DontCache(result)

    return result
