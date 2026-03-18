"""
Seed competitor data for demo purposes - Nestle brands and their market competitors.
This ensures reliable, realistic data for investor demos without API dependencies.
"""

COMPETITOR_DATABASE: dict[str, list[dict]] = {
    # --- Chocolate / Confectionery ---
    "kitkat": [
        {
            "name": "Cadbury Dairy Milk",
            "product": "Cadbury Dairy Milk Chocolate Bar",
            "tagline": "There's a glass and a half in everyone",
            "description": "Rich, creamy milk chocolate made with a glass and a half of fresh milk in every bar. The UK's favourite chocolate, perfect for sharing moments of joy.",
            "market_position": "Market leader in milk chocolate segment with 26% global confectionery share",
        },
        {
            "name": "Snickers",
            "product": "Snickers Chocolate Bar",
            "tagline": "You're Not You When You're Hungry",
            "description": "Packed with roasted peanuts, nougat, and caramel covered in milk chocolate. Snickers satisfies your hunger with a perfect combination of taste and energy.",
            "market_position": "World's best-selling candy bar with $3.7B annual revenue",
        },
        {
            "name": "Kinder",
            "product": "Kinder Bueno",
            "tagline": "A little treat goes a long way",
            "description": "Crispy wafer shell with a smooth milky and hazelnut filling, covered in milk chocolate. Kinder Bueno is the premium snacking indulgence for discerning chocolate lovers.",
            "market_position": "Fastest-growing premium chocolate brand, 15% YoY growth in key markets",
        },
    ],
    # --- Coffee ---
    "nescafe": [
        {
            "name": "Starbucks",
            "product": "Starbucks VIA Instant Coffee",
            "tagline": "To inspire and nurture the human spirit",
            "description": "Premium micro-ground instant coffee that delivers the rich, smooth taste you expect from Starbucks. Crafted from the finest arabica beans for an elevated at-home coffee experience.",
            "market_position": "Global coffeehouse leader with 35,711 stores and dominant retail presence",
        },
        {
            "name": "Lavazza",
            "product": "Lavazza Qualita Rossa",
            "tagline": "Italy's Favourite Coffee",
            "description": "A harmonious blend of Arabica and Robusta beans from Brazil and Africa. Rich, full-bodied coffee with a chocolate aftertaste -- authentic Italian coffee heritage in every cup.",
            "market_position": "Italy's No.1 coffee brand, present in 140+ countries with EUR2.9B revenue",
        },
        {
            "name": "Folgers",
            "product": "Folgers Classic Roast",
            "tagline": "The Best Part of Wakin' Up Is Folgers in Your Cup",
            "description": "America's beloved morning ritual. Medium roast ground coffee with a smooth, rich flavor that's been waking up America for over 170 years.",
            "market_position": "Best-selling retail coffee in the US with 21% market share",
        },
    ],
    # --- Instant Noodles / Quick Meals ---
    "maggi": [
        {
            "name": "Indomie",
            "product": "Indomie Mi Goreng",
            "tagline": "Indomie Seleraku",
            "description": "Indonesia's iconic instant fried noodles with a signature blend of sweet soy sauce, chili, and seasoned oil. Loved by billions across 100+ countries for its bold, authentic flavor.",
            "market_position": "World's most consumed instant noodle brand, 30B+ servings/year",
        },
        {
            "name": "Nissin",
            "product": "Cup Noodles",
            "tagline": "Hungry? Get Cup Noodles",
            "description": "The original instant ramen in a cup -- just add hot water. Convenient, flavorful, and ready in 3 minutes. A global icon of quick, satisfying meals.",
            "market_position": "Pioneer of instant noodles, present in 100+ countries, $4.5B annual revenue",
        },
        {
            "name": "Knorr",
            "product": "Knorr Noodles",
            "tagline": "Eat Good. Feel Good.",
            "description": "Delicious and wholesome noodles enriched with carefully selected real ingredients and seasonings. Part of Unilever's commitment to making nutritious food accessible to all.",
            "market_position": "Unilever's largest food brand, EUR3.5B annual sales across 87 countries",
        },
    ],
    # --- Baby Food / Nutrition ---
    "cerelac": [
        {
            "name": "Gerber",
            "product": "Gerber Baby Cereal",
            "tagline": "Anything for Baby",
            "description": "Trusted by parents for over 90 years, Gerber cereals are specially formulated with iron, zinc, and essential vitamins to support your baby's growth and development.",
            "market_position": "America's #1 baby food brand with 70%+ market share in infant cereals",
        },
        {
            "name": "Heinz Baby",
            "product": "Heinz Baby Cereal",
            "tagline": "Growing Up with Heinz",
            "description": "Nutritious baby cereals made with carefully sourced whole grains and fortified with essential nutrients. Smooth texture perfect for baby's first foods journey.",
            "market_position": "Leading baby food brand in UK/Australia with strong heritage positioning",
        },
        {
            "name": "Hipp Organic",
            "product": "HiPP Organic Baby Cereal",
            "tagline": "The best from nature. The best for nature.",
            "description": "100% organic baby cereals with no artificial additives. Made from sustainably farmed ingredients with the highest organic standards for your baby's health.",
            "market_position": "Europe's leading organic baby food brand, strong in health-conscious segments",
        },
    ],
    # --- Bottled Water ---
    "pure life": [
        {
            "name": "Evian",
            "product": "Evian Natural Mineral Water",
            "tagline": "Live Young",
            "description": "Naturally filtered through glacial rocks for over 15 years, Evian natural mineral water has a unique mineral composition and crisp, clean taste from the French Alps.",
            "market_position": "World's leading premium water brand, distributed in 150+ countries",
        },
        {
            "name": "Fiji Water",
            "product": "FIJI Natural Artesian Water",
            "tagline": "Earth's Finest Water",
            "description": "Naturally purified volcanic rock-filtered artesian water from the remote Yaqara Valley of Viti Levu. Soft, smooth taste with natural minerals and electrolytes.",
            "market_position": "Leading premium imported water in the US, iconic luxury positioning",
        },
        {
            "name": "Dasani",
            "product": "Dasani Purified Water",
            "tagline": "Treat Yourself Well. Every Day.",
            "description": "Enhanced with minerals for a pure, fresh taste. Dasani uses reverse osmosis filtration and a proprietary mineral blend for consistently clean, crisp hydration.",
            "market_position": "Coca-Cola's flagship water brand, #2 in US bottled water market",
        },
    ],
    # --- Pet Food ---
    "purina": [
        {
            "name": "Royal Canin",
            "product": "Royal Canin Dog Food",
            "tagline": "Incredible in every detail",
            "description": "Breed-specific and health-focused nutrition backed by veterinary science. Each formula precisely tailored to your pet's size, breed, age, and health needs.",
            "market_position": "World's leading premium pet nutrition brand, EUR4.5B revenue (Mars Inc.)",
        },
        {
            "name": "Blue Buffalo",
            "product": "Blue Buffalo Life Protection",
            "tagline": "Love them like family. Feed them like family.",
            "description": "Natural pet food made with real meat, whole grains, and garden veggies. No chicken by-product meals, corn, wheat, or soy. LifeSource Bits for precise antioxidant nutrition.",
            "market_position": "Fastest-growing natural pet food brand in US, acquired by General Mills",
        },
        {
            "name": "Hill's Science Diet",
            "product": "Hill's Science Diet",
            "tagline": "Nutrition that transforms lives",
            "description": "Clinically proven nutrition developed by 220+ veterinary scientists. Precise, balanced formulas to address specific health needs from puppyhood through senior years.",
            "market_position": "#1 vet-recommended pet food brand globally, $3.6B annual revenue",
        },
    ],
}


def get_competitors(brand_name: str, product_category: str) -> list[dict] | None:
    """Look up competitors by brand name, falling back to category keywords."""
    key = brand_name.strip().lower()
    if key in COMPETITOR_DATABASE:
        return COMPETITOR_DATABASE[key]

    # Fuzzy category match
    category_lower = product_category.strip().lower()
    keyword_map = {
        "chocolate": "kitkat",
        "confectionery": "kitkat",
        "candy": "kitkat",
        "wafer": "kitkat",
        "coffee": "nescafe",
        "instant coffee": "nescafe",
        "noodle": "maggi",
        "instant noodle": "maggi",
        "pasta": "maggi",
        "baby": "cerelac",
        "infant": "cerelac",
        "cereal": "cerelac",
        "water": "pure life",
        "bottled water": "pure life",
        "pet": "purina",
        "dog": "purina",
        "cat": "purina",
        "pet food": "purina",
    }
    for keyword, db_key in keyword_map.items():
        if keyword in category_lower:
            return COMPETITOR_DATABASE[db_key]
    return None
