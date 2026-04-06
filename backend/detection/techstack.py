"""Detect technology stack from raw HTML using simple string / regex matching.

Includes general web tech detection PLUS industry-specific software detection
(healthcare/EHR, restaurant POS, salon booking, legal, real estate, etc.).
"""
from __future__ import annotations

import re
from typing import Optional

# Each entry: (technology_name, list_of_signatures, optional_cms_label, optional_framework_label)
_SIGNATURES: list[tuple[str, list[str], Optional[str], Optional[str]]] = [
    # CMS platforms
    ("WordPress",    ["wp-content", "wp-includes"],                     "WordPress",    None),
    ("Shopify",      ["cdn.shopify.com", "Shopify.theme"],              "Shopify",      None),
    ("Wix",          ["wix.com", "X-Wix"],                              "Wix",          None),
    ("Squarespace",  ["squarespace.com", "static.squarespace"],         "Squarespace",  None),
    ("Webflow",      ["webflow.com"],                                   "Webflow",      None),
    ("Ghost",        ["ghost.org"],                                     "Ghost",        None),
    ("Drupal",       ["drupal.js", "Drupal.settings"],                  "Drupal",       None),
    ("Joomla",       ["/media/jui/"],                                   "Joomla",       None),
    # Frameworks
    ("React",        ["_reactRoot", "__REACT", "react-root"],           None,           "React"),
    ("Next.js",      ["__NEXT_DATA__", "_next/"],                       None,           "Next.js"),
    ("Vue.js",       ["__vue", "Vue.js"],                               None,           "Vue.js"),
    ("Angular",      ["ng-version", "ng-app"],                          None,           "Angular"),
]

# Additional general technology signatures
_EXTRA_TECH: list[tuple[str, list[str]]] = [
    ("WooCommerce",          ["woocommerce", "wc-ajax"]),
    ("jQuery",               ["jquery.min.js", "jquery.js"]),
    ("Bootstrap",            ["bootstrap.min.css", "bootstrap.min.js"]),
    ("Tailwind CSS",         ["tailwindcss", "tailwind.min.css"]),
    ("Google Tag Manager",   ["googletagmanager.com/gtm.js"]),
]

# ---------------------------------------------------------------------------
# Industry-specific software detection
# ---------------------------------------------------------------------------
# Each entry: (software_name, category, list_of_signatures)

_INDUSTRY_SOFTWARE: list[tuple[str, str, list[str]]] = [
    # --- Healthcare / Medical ---
    # Patient Portals & EHR
    ("Athenahealth",        "healthcare_ehr",   ["athenahealth", "athenanet", "athena-"]),
    ("Epic MyChart",        "healthcare_ehr",   ["mychart", "epic.com", "epicmychart"]),
    ("Cerner",              "healthcare_ehr",   ["cerner.com", "cerner-", "cernerhealth"]),
    ("eClinicalWorks",      "healthcare_ehr",   ["eclinicalworks", "ecwcloud"]),
    ("DrChrono",            "healthcare_ehr",   ["drchrono"]),
    ("Practice Fusion",     "healthcare_ehr",   ["practicefusion"]),
    ("Kareo",               "healthcare_ehr",   ["kareo.com", "kareo-"]),
    ("AdvancedMD",          "healthcare_ehr",   ["advancedmd"]),
    ("NextGen",             "healthcare_ehr",   ["nextgen.com", "nextgen-"]),
    ("Allscripts",          "healthcare_ehr",   ["allscripts"]),
    ("ModMed",              "healthcare_ehr",   ["modmed.com", "modernizing-medicine"]),
    ("SimplePractice",      "healthcare_ehr",   ["simplepractice"]),
    ("TherapyNotes",        "healthcare_ehr",   ["therapynotes"]),
    ("Jane App",            "healthcare_ehr",   ["janeapp.com", "jane.app"]),
    # Online scheduling / patient intake
    ("Zocdoc",              "healthcare_scheduling", ["zocdoc"]),
    ("PatientPop",          "healthcare_scheduling", ["patientpop"]),
    ("Phreesia",            "healthcare_scheduling", ["phreesia"]),
    ("Solutionreach",       "healthcare_scheduling", ["solutionreach"]),
    ("Lighthouse 360",      "healthcare_scheduling", ["lh360", "lighthouse360"]),
    ("NexHealth",           "healthcare_scheduling", ["nexhealth"]),

    # --- Dental ---
    ("Dentrix",             "dental_software",  ["dentrix"]),
    ("Open Dental",         "dental_software",  ["opendental"]),
    ("Eaglesoft",           "dental_software",  ["eaglesoft"]),
    ("CareStack",           "dental_software",  ["carestack"]),
    ("Curve Dental",        "dental_software",  ["curvedental"]),
    ("Weave",               "dental_software",  ["getweave.com", "weave-"]),
    ("RevenueWell",         "dental_software",  ["revenuewell"]),

    # --- Restaurant / Food ---
    ("Toast POS",           "restaurant_pos",   ["toasttab.com", "toast-"]),
    ("Square",              "restaurant_pos",   ["squareup.com", "square-"]),
    ("Clover",              "restaurant_pos",   ["clover.com"]),
    ("Revel Systems",       "restaurant_pos",   ["revelsystems"]),
    ("Lightspeed",          "restaurant_pos",   ["lightspeedhq.com"]),
    ("TouchBistro",         "restaurant_pos",   ["touchbistro"]),
    ("Aloha POS",           "restaurant_pos",   ["aloha-pos", "ncr.com/restaurant"]),
    # Online ordering
    ("DoorDash Storefront", "restaurant_ordering", ["doordash.com", "storefront.doordash"]),
    ("ChowNow",             "restaurant_ordering", ["chownow.com", "ordering.chownow"]),
    ("Grubhub",             "restaurant_ordering", ["grubhub.com"]),
    ("UberEats",            "restaurant_ordering", ["ubereats.com"]),
    ("BentoBox",            "restaurant_ordering", ["bentobox.com", "getbento.com"]),
    ("Olo",                 "restaurant_ordering", ["olo.com"]),
    # Reservations
    ("OpenTable",           "restaurant_reservations", ["opentable.com", "opentable-"]),
    ("Resy",                "restaurant_reservations", ["resy.com"]),
    ("Yelp Reservations",   "restaurant_reservations", ["yelp.com/reservations"]),

    # --- Salon / Spa / Beauty ---
    ("Mindbody",            "salon_booking",    ["mindbodyonline.com", "mindbody-"]),
    ("Vagaro",              "salon_booking",    ["vagaro.com"]),
    ("Booksy",              "salon_booking",    ["booksy.com"]),
    ("Fresha",              "salon_booking",    ["fresha.com"]),
    ("GlossGenius",         "salon_booking",    ["glossgenius.com"]),
    ("Boulevard",           "salon_booking",    ["joinblvd.com"]),
    ("Acuity Scheduling",   "salon_booking",    ["acuityscheduling.com"]),
    ("Square Appointments", "salon_booking",    ["squareup.com/appointments"]),

    # --- Fitness / Gym ---
    ("Mindbody",            "fitness_software", ["mindbodyonline.com"]),
    ("Wodify",              "fitness_software", ["wodify.com"]),
    ("Zen Planner",         "fitness_software", ["zenplanner.com"]),
    ("Glofox",              "fitness_software", ["glofox.com"]),
    ("PushPress",           "fitness_software", ["pushpress.com"]),
    ("Pike13",              "fitness_software", ["pike13.com"]),

    # --- Legal ---
    ("Clio",                "legal_software",   ["clio.com", "app.clio"]),
    ("MyCase",              "legal_software",   ["mycase.com"]),
    ("PracticePanther",     "legal_software",   ["practicepanther.com"]),
    ("Smokeball",           "legal_software",   ["smokeball.com"]),
    ("LawPay",              "legal_payment",    ["lawpay.com"]),
    ("Avvo",                "legal_directory",  ["avvo.com"]),
    ("FindLaw",             "legal_directory",  ["findlaw.com"]),

    # --- Real Estate ---
    ("IDX Broker",          "real_estate",      ["idxbroker.com"]),
    ("Zillow",              "real_estate",      ["zillow.com"]),
    ("Realtor.com",         "real_estate",      ["realtor.com"]),
    ("kvCORE",              "real_estate",      ["kvcore.com"]),
    ("BoomTown",            "real_estate",      ["boomtownroi.com"]),
    ("Sierra Interactive",  "real_estate",      ["sierrainteractive.com"]),
    ("Chime CRM",           "real_estate",      ["chime.me"]),

    # --- E-commerce ---
    ("BigCommerce",         "ecommerce",        ["bigcommerce.com"]),
    ("Magento",             "ecommerce",        ["magento", "mage-"]),
    ("PrestaShop",          "ecommerce",        ["prestashop"]),
    ("Stripe",              "payment",          ["stripe.com", "js.stripe.com"]),
    ("PayPal",              "payment",          ["paypal.com", "paypalobjects"]),
    ("Braintree",           "payment",          ["braintreegateway.com"]),

    # --- Scheduling / Booking (general) ---
    ("Calendly",            "scheduling",       ["calendly.com"]),
    ("HubSpot Meetings",    "scheduling",       ["meetings.hubspot.com"]),
    ("Setmore",             "scheduling",       ["setmore.com"]),
    ("SimplyBook.me",       "scheduling",       ["simplybook.me"]),
    ("Appointy",            "scheduling",       ["appointy.com"]),

    # --- CRM / Marketing ---
    ("HubSpot",             "crm",              ["hubspot.com", "hs-scripts.com", "hbspt.forms"]),
    ("Salesforce",          "crm",              ["salesforce.com", "force.com"]),
    ("Zoho",                "crm",              ["zoho.com"]),
    ("Mailchimp",           "email_marketing",  ["mailchimp.com", "mc.js"]),
    ("Constant Contact",    "email_marketing",  ["constantcontact.com"]),
    ("Klaviyo",             "email_marketing",  ["klaviyo.com"]),
    ("ActiveCampaign",      "email_marketing",  ["activecampaign.com"]),

    # --- Live Chat / Support ---
    ("Intercom",            "live_chat",        ["intercom.io", "intercomcdn"]),
    ("Drift",               "live_chat",        ["drift.com", "js.driftt.com"]),
    ("Zendesk",             "live_chat",        ["zendesk.com", "zopim.com"]),
    ("Tidio",               "live_chat",        ["tidio.co"]),
    ("LiveChat",            "live_chat",        ["livechatinc.com"]),
    ("Crisp",               "live_chat",        ["crisp.chat"]),
    ("Tawk.to",             "live_chat",        ["tawk.to"]),

    # --- Reviews / Reputation ---
    ("Birdeye",             "reputation",       ["birdeye.com"]),
    ("Podium",              "reputation",       ["podium.com"]),
    ("Trustpilot",          "reputation",       ["trustpilot.com"]),
    ("Google Reviews Widget", "reputation",     ["elfsight.com/google-review", "reviewsonmywebsite"]),
]


def detect_tech_stack(html: str) -> dict:
    """Scan *html* for known technology signatures.

    Returns::

        {
            "technologies": ["WordPress", "WooCommerce", ...],
            "cms": "WordPress" | None,
            "framework": "React" | None,
            "software": {
                "healthcare_ehr": ["Epic MyChart"],
                "restaurant_pos": ["Toast POS"],
                ...
            },
            "software_list": ["Epic MyChart", "Toast POS", ...],
        }
    """
    if not html:
        return {"technologies": [], "cms": None, "framework": None, "software": {}, "software_list": []}

    html_lower = html.lower()
    technologies: list[str] = []
    cms: Optional[str] = None
    framework: Optional[str] = None

    # General tech detection
    for tech_name, signatures, cms_label, fw_label in _SIGNATURES:
        for sig in signatures:
            if sig.lower() in html_lower:
                if tech_name not in technologies:
                    technologies.append(tech_name)
                if cms_label and cms is None:
                    cms = cms_label
                if fw_label and framework is None:
                    framework = fw_label
                break

    for tech_name, signatures in _EXTRA_TECH:
        for sig in signatures:
            if sig.lower() in html_lower:
                if tech_name not in technologies:
                    technologies.append(tech_name)
                break

    # Industry-specific software detection
    software: dict[str, list[str]] = {}
    software_list: list[str] = []

    for sw_name, category, signatures in _INDUSTRY_SOFTWARE:
        for sig in signatures:
            if sig.lower() in html_lower:
                software.setdefault(category, [])
                if sw_name not in software[category]:
                    software[category].append(sw_name)
                if sw_name not in software_list:
                    software_list.append(sw_name)
                break

    return {
        "technologies": technologies,
        "cms": cms,
        "framework": framework,
        "software": software,
        "software_list": software_list,
    }
