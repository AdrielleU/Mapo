"""
US states to major cities mapping.

Provides lookup functions used by the API to populate the state/city
dropdowns in the structured search UI.
"""

US_STATE_CITIES = {
    "Alabama": [
        "Birmingham", "Montgomery", "Huntsville", "Mobile", "Tuscaloosa",
        "Hoover", "Dothan", "Auburn", "Decatur", "Madison",
    ],
    "Alaska": [
        "Anchorage", "Fairbanks", "Juneau", "Sitka", "Ketchikan",
        "Wasilla", "Kenai", "Kodiak",
    ],
    "Arizona": [
        "Phoenix", "Tucson", "Mesa", "Chandler", "Scottsdale",
        "Glendale", "Gilbert", "Tempe", "Peoria", "Surprise",
        "Yuma", "Avondale", "Goodyear", "Flagstaff", "Buckeye",
        "Casa Grande", "Lake Havasu City", "Maricopa", "Sierra Vista", "Prescott",
    ],
    "Arkansas": [
        "Little Rock", "Fort Smith", "Fayetteville", "Springdale", "Jonesboro",
        "North Little Rock", "Conway", "Rogers", "Pine Bluff", "Bentonville",
    ],
    "California": [
        "Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno",
        "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim",
        "Santa Ana", "Riverside", "Stockton", "Irvine", "Chula Vista",
        "Fremont", "San Bernardino", "Modesto", "Moreno Valley", "Fontana",
        "Glendale", "Huntington Beach", "Santa Clarita", "Garden Grove", "Oceanside",
        "Rancho Cucamonga", "Ontario", "Santa Rosa", "Elk Grove", "Corona",
        "Lancaster", "Palmdale", "Salinas", "Pomona", "Escondido",
        "Torrance", "Pasadena", "Sunnyvale", "Orange", "Fullerton",
    ],
    "Colorado": [
        "Denver", "Colorado Springs", "Aurora", "Fort Collins", "Lakewood",
        "Thornton", "Arvada", "Westminster", "Pueblo", "Centennial",
        "Boulder", "Highlands Ranch", "Greeley", "Longmont", "Loveland",
        "Grand Junction", "Broomfield", "Castle Rock", "Commerce City", "Parker",
    ],
    "Connecticut": [
        "Bridgeport", "New Haven", "Hartford", "Stamford", "Waterbury",
        "Norwalk", "Danbury", "New Britain", "West Hartford", "Greenwich",
    ],
    "Delaware": [
        "Wilmington", "Dover", "Newark", "Middletown", "Bear",
        "Brookside", "Glasgow", "Hockessin",
    ],
    "Florida": [
        "Jacksonville", "Miami", "Tampa", "Orlando", "St. Petersburg",
        "Hialeah", "Tallahassee", "Fort Lauderdale", "Port St. Lucie", "Cape Coral",
        "Pembroke Pines", "Hollywood", "Miramar", "Gainesville", "Coral Springs",
        "Miami Gardens", "Clearwater", "Palm Bay", "Pompano Beach", "West Palm Beach",
        "Lakeland", "Davie", "Boca Raton", "Sunrise", "Deltona",
        "Plantation", "Fort Myers", "Deerfield Beach", "Kissimmee", "Sarasota",
    ],
    "Georgia": [
        "Atlanta", "Augusta", "Columbus", "Macon", "Savannah",
        "Athens", "Sandy Springs", "Roswell", "Johns Creek", "Albany",
        "Warner Robins", "Alpharetta", "Marietta", "Valdosta", "Smyrna",
        "Dunwoody", "Brookhaven", "Peachtree City", "Newnan", "Dalton",
    ],
    "Hawaii": [
        "Honolulu", "Pearl City", "Hilo", "Kailua", "Waipahu",
        "Kaneohe", "Mililani Town", "Kahului",
    ],
    "Idaho": [
        "Boise", "Meridian", "Nampa", "Idaho Falls", "Caldwell",
        "Pocatello", "Coeur d'Alene", "Twin Falls", "Post Falls", "Lewiston",
    ],
    "Illinois": [
        "Chicago", "Aurora", "Rockford", "Joliet", "Naperville",
        "Springfield", "Peoria", "Elgin", "Waukegan", "Champaign",
        "Bloomington", "Decatur", "Evanston", "Des Plaines", "Berwyn",
        "Wheaton", "Belleville", "Elmhurst", "DeKalb", "Moline",
        "Arlington Heights", "Schaumburg", "Bolingbrook", "Palatine", "Skokie",
    ],
    "Indiana": [
        "Indianapolis", "Fort Wayne", "Evansville", "South Bend", "Carmel",
        "Fishers", "Bloomington", "Hammond", "Gary", "Lafayette",
        "Muncie", "Terre Haute", "Kokomo", "Noblesville", "Anderson",
    ],
    "Iowa": [
        "Des Moines", "Cedar Rapids", "Davenport", "Sioux City", "Iowa City",
        "Waterloo", "Council Bluffs", "Ames", "West Des Moines", "Dubuque",
    ],
    "Kansas": [
        "Wichita", "Overland Park", "Kansas City", "Olathe", "Topeka",
        "Lawrence", "Shawnee", "Manhattan", "Lenexa", "Salina",
    ],
    "Kentucky": [
        "Louisville", "Lexington", "Bowling Green", "Owensboro", "Covington",
        "Richmond", "Georgetown", "Florence", "Hopkinsville", "Nicholasville",
    ],
    "Louisiana": [
        "New Orleans", "Baton Rouge", "Shreveport", "Lafayette", "Lake Charles",
        "Kenner", "Bossier City", "Monroe", "Alexandria", "Houma",
    ],
    "Maine": [
        "Portland", "Lewiston", "Bangor", "South Portland", "Auburn",
        "Biddeford", "Sanford", "Saco",
    ],
    "Maryland": [
        "Baltimore", "Frederick", "Rockville", "Gaithersburg", "Bowie",
        "Hagerstown", "Annapolis", "College Park", "Salisbury", "Laurel",
        "Greenbelt", "Cumberland", "Hyattsville", "Elkton", "Bethesda",
    ],
    "Massachusetts": [
        "Boston", "Worcester", "Springfield", "Lowell", "Cambridge",
        "New Bedford", "Brockton", "Quincy", "Lynn", "Fall River",
        "Newton", "Lawrence", "Somerville", "Framingham", "Haverhill",
        "Waltham", "Malden", "Brookline", "Plymouth", "Medford",
    ],
    "Michigan": [
        "Detroit", "Grand Rapids", "Warren", "Sterling Heights", "Ann Arbor",
        "Lansing", "Flint", "Dearborn", "Livonia", "Troy",
        "Westland", "Farmington Hills", "Kalamazoo", "Wyoming", "Southfield",
        "Rochester Hills", "Taylor", "Pontiac", "St. Clair Shores", "Royal Oak",
    ],
    "Minnesota": [
        "Minneapolis", "Saint Paul", "Rochester", "Duluth", "Bloomington",
        "Brooklyn Park", "Plymouth", "Maple Grove", "Woodbury", "St. Cloud",
        "Eagan", "Eden Prairie", "Coon Rapids", "Burnsville", "Blaine",
        "Lakeville", "Minnetonka", "Apple Valley", "Edina", "Mankato",
    ],
    "Mississippi": [
        "Jackson", "Gulfport", "Southaven", "Hattiesburg", "Biloxi",
        "Meridian", "Tupelo", "Olive Branch", "Greenville", "Horn Lake",
    ],
    "Missouri": [
        "Kansas City", "St. Louis", "Springfield", "Columbia", "Independence",
        "Lee's Summit", "O'Fallon", "St. Joseph", "St. Charles", "Blue Springs",
        "St. Peters", "Florissant", "Joplin", "Chesterfield", "Jefferson City",
    ],
    "Montana": [
        "Billings", "Missoula", "Great Falls", "Bozeman", "Butte",
        "Helena", "Kalispell", "Havre",
    ],
    "Nebraska": [
        "Omaha", "Lincoln", "Bellevue", "Grand Island", "Kearney",
        "Fremont", "Hastings", "Norfolk", "North Platte", "Columbus",
    ],
    "Nevada": [
        "Las Vegas", "Henderson", "Reno", "North Las Vegas", "Sparks",
        "Carson City", "Elko", "Mesquite", "Boulder City", "Fernley",
    ],
    "New Hampshire": [
        "Manchester", "Nashua", "Concord", "Derry", "Dover",
        "Rochester", "Salem", "Merrimack",
    ],
    "New Jersey": [
        "Newark", "Jersey City", "Paterson", "Elizabeth", "Edison",
        "Woodbridge", "Lakewood", "Toms River", "Hamilton", "Trenton",
        "Clifton", "Camden", "Brick", "Cherry Hill", "Passaic",
        "Union City", "Old Bridge", "Middletown", "Gloucester", "North Bergen",
    ],
    "New Mexico": [
        "Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe", "Roswell",
        "Farmington", "Clovis", "Hobbs", "Alamogordo", "Carlsbad",
    ],
    "New York": [
        "New York City", "Buffalo", "Rochester", "Yonkers", "Syracuse",
        "Albany", "New Rochelle", "Mount Vernon", "Schenectady", "Utica",
        "White Plains", "Hempstead", "Troy", "Niagara Falls", "Binghamton",
        "Freeport", "Valley Stream", "Long Beach", "Spring Valley", "Rome",
        "Ithaca", "Poughkeepsie", "North Tonawanda", "Jamestown", "Saratoga Springs",
    ],
    "North Carolina": [
        "Charlotte", "Raleigh", "Greensboro", "Durham", "Winston-Salem",
        "Fayetteville", "Cary", "Wilmington", "High Point", "Concord",
        "Greenville", "Asheville", "Gastonia", "Jacksonville", "Chapel Hill",
        "Huntersville", "Apex", "Burlington", "Mooresville", "Rocky Mount",
    ],
    "North Dakota": [
        "Fargo", "Bismarck", "Grand Forks", "Minot", "West Fargo",
        "Williston", "Dickinson", "Mandan",
    ],
    "Ohio": [
        "Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron",
        "Dayton", "Parma", "Canton", "Youngstown", "Lorain",
        "Hamilton", "Springfield", "Kettering", "Elyria", "Lakewood",
        "Cuyahoga Falls", "Middletown", "Newark", "Mentor", "Dublin",
    ],
    "Oklahoma": [
        "Oklahoma City", "Tulsa", "Norman", "Broken Arrow", "Edmond",
        "Lawton", "Moore", "Midwest City", "Enid", "Stillwater",
    ],
    "Oregon": [
        "Portland", "Salem", "Eugene", "Gresham", "Hillsboro",
        "Beaverton", "Bend", "Medford", "Springfield", "Corvallis",
        "Albany", "Tigard", "Lake Oswego", "Keizer", "Grants Pass",
    ],
    "Pennsylvania": [
        "Philadelphia", "Pittsburgh", "Allentown", "Reading", "Scranton",
        "Bethlehem", "Lancaster", "Harrisburg", "York", "State College",
        "Wilkes-Barre", "Erie", "Easton", "Lebanon", "Hazleton",
        "Chester", "Norristown", "Chambersburg", "Williamsport", "Pottstown",
    ],
    "Rhode Island": [
        "Providence", "Warwick", "Cranston", "Pawtucket", "East Providence",
        "Woonsocket", "Newport", "Central Falls",
    ],
    "South Carolina": [
        "Columbia", "Charleston", "North Charleston", "Mount Pleasant", "Rock Hill",
        "Greenville", "Summerville", "Goose Creek", "Hilton Head", "Florence",
    ],
    "South Dakota": [
        "Sioux Falls", "Rapid City", "Aberdeen", "Brookings", "Watertown",
        "Mitchell", "Yankton", "Huron",
    ],
    "Tennessee": [
        "Nashville", "Memphis", "Knoxville", "Chattanooga", "Clarksville",
        "Murfreesboro", "Franklin", "Jackson", "Johnson City", "Bartlett",
        "Hendersonville", "Kingsport", "Collierville", "Smyrna", "Cleveland",
    ],
    "Texas": [
        "Houston", "San Antonio", "Dallas", "Austin", "Fort Worth",
        "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo",
        "Lubbock", "Garland", "Irving", "Amarillo", "Grand Prairie",
        "Brownsville", "McKinney", "Frisco", "Pasadena", "Mesquite",
        "Killeen", "McAllen", "Midland", "Waco", "Denton",
        "Carrollton", "Round Rock", "Lewisville", "Odessa", "Abilene",
        "Richardson", "Allen", "Sugar Land", "Beaumont", "Tyler",
        "League City", "College Station", "San Marcos", "Pearland", "Edinburg",
    ],
    "Utah": [
        "Salt Lake City", "West Valley City", "Provo", "West Jordan", "Orem",
        "Sandy", "Ogden", "St. George", "Layton", "South Jordan",
        "Lehi", "Millcreek", "Taylorsville", "Logan", "Murray",
    ],
    "Vermont": [
        "Burlington", "South Burlington", "Rutland", "Barre", "Montpelier",
        "St. Albans", "Winooski", "Bennington",
    ],
    "Virginia": [
        "Virginia Beach", "Norfolk", "Chesapeake", "Richmond", "Newport News",
        "Alexandria", "Hampton", "Roanoke", "Portsmouth", "Suffolk",
        "Lynchburg", "Harrisonburg", "Leesburg", "Charlottesville", "Danville",
        "Manassas", "Fredericksburg", "Winchester", "Salem", "Herndon",
    ],
    "Washington": [
        "Seattle", "Spokane", "Tacoma", "Vancouver", "Bellevue",
        "Kent", "Everett", "Renton", "Spokane Valley", "Federal Way",
        "Yakima", "Kirkland", "Bellingham", "Kennewick", "Auburn",
        "Olympia", "Pasco", "Redmond", "Lakewood", "Sammamish",
    ],
    "West Virginia": [
        "Charleston", "Huntington", "Morgantown", "Parkersburg", "Wheeling",
        "Weirton", "Fairmont", "Martinsburg",
    ],
    "Wisconsin": [
        "Milwaukee", "Madison", "Green Bay", "Kenosha", "Racine",
        "Appleton", "Waukesha", "Eau Claire", "Oshkosh", "Janesville",
        "West Allis", "La Crosse", "Sheboygan", "Wauwatosa", "Fond du Lac",
    ],
    "Wyoming": [
        "Cheyenne", "Casper", "Laramie", "Gillette", "Rock Springs",
        "Sheridan", "Green River", "Evanston",
    ],
    "District of Columbia": [
        "Washington",
    ],
}


def get_states(country_code="US"):
    """Return list of state/region names for a country."""
    if country_code == "US":
        return sorted(US_STATE_CITIES.keys())
    return []


def get_state_cities(country_code, state_name):
    """Return cities for a given state."""
    if country_code == "US":
        return US_STATE_CITIES.get(state_name, [])
    return []
