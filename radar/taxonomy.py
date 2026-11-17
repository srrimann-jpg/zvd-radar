"""The diamond + jewellery domain model.

Everything the radar knows about the industry lives here: which themes exist, which words
signal them, who the audience is, and what a publishable content brief looks like for each.
Edit this file to tune the listener; no other module needs to know the vocabulary.
"""

# weight = commercial value of the theme to a diamond marketplace (1 quiet -> 5 money)
THEMES = [
    {
        "id": "lab-grown",
        "label": "Lab-grown diamonds",
        "weight": 5,
        "terms": [
            "lab grown", "lab-grown", "lab created", "lab-created", "lab diamond",
            "lab diamonds", "cvd", "hpht", "synthetic diamond", "cultured diamond",
            "man made diamond", "lightbox", "grown diamond", "laboratory grown",
        ],
        "b2b": ["producer", "manufacturer", "capacity", "factory", "oversupply", "surat",
                "wholesale", "trade", "supply glut", "inventory", "chip", "semiconductor"],
        "b2c": ["ring", "earrings", "necklace", "bracelet", "gift", "bride", "cheaper",
                "worth it", "should i", "vs", "engagement"],
        "angle": "Publish a like-for-like comparison with real price examples, then own the 'vs' searches with one definitive page.",
        "formats": "Comparison guide + FAQ block + 3 short videos",
        "hook": "Buyers are not confused about what lab-grown is any more - they are confused about what it is worth next to natural.",
        "outline": [
            "The 30-second answer to {kw}, above the fold",
            "Price per carat today: lab-grown vs natural, with live marketplace examples",
            "What the certificate says (IGI/CVD language explained in plain English)",
            "Resale reality: what each stone is worth after purchase",
            "Who each stone is right for - with three real buyer scenarios",
            "Checklist: five questions to ask before paying a deposit",
        ],
        "cta": "Browse certified lab-grown stones on ZVDapp with price-per-carat visible",
    },
    {
        "id": "natural-diamond",
        "label": "Natural & mined diamonds",
        "weight": 4,
        "terms": [
            "natural diamond", "natural diamonds", "mined diamond", "earth mined",
            "earth-mined", "rough diamond", "rough diamonds", "de beers", "alrosa",
            "botswana", "angola", "diamond mine", "diamond mining", "kimberlite",
        ],
        "b2b": ["mine", "mining", "stake", "production", "supply agreement", "sightholder",
                "tender", "producer", "government"],
        "b2c": ["ring", "bride", "heirloom", "engagement", "should i buy", "worth"],
        "angle": "Translate supply-side news into buyer confidence: what scarcity, ownership and production cuts mean for the person buying a stone this quarter.",
        "formats": "Market explainer + newsletter section",
        "hook": "The supply story is moving faster than buyers realise, and the gap is where trust is won or lost.",
        "outline": [
            "What changed this week, in one paragraph a buyer can repeat",
            "Why {kw} matters to the price on your screen",
            "Natural vs lab-grown supply, side by side for the year",
            "What this means for resale and heirloom value",
            "How ZVDapp prices around it (and how to read a quote)",
        ],
        "cta": "See natural diamond inventory with origin and certificate on ZVDapp",
    },
    {
        "id": "diamond-prices",
        "label": "Prices & pricing",
        "weight": 5,
        "terms": [
            "diamond price", "diamond prices", "price per carat", "prices fall", "prices rise",
            "price drop", "pricing", "expensive", "cheaper", "discount", "premium",
            "cost of", "price index", "rapaport", "inflation", "price crash",
        ],
        "b2b": ["margin", "wholesale", "trade", "index", "list price", "dealer", "inventory value"],
        "b2c": ["how much", "budget", "cheap", "affordable", "worth", "cost", "price of"],
        "angle": "Publish a transparent price-per-carat benchmark, refreshed monthly, so ZVDapp becomes the page people cite when they argue about diamond prices.",
        "formats": "Data page + monthly update + short video",
        "hook": "Diamond pricing is opaque by design, which means a clear, sourced price table is a permanent traffic asset.",
        "outline": [
            "Price per carat by shape and size band, this month vs last",
            "Why {kw} - the three factors that actually move it",
            "Lab-grown vs natural price curves on one chart",
            "What a fair retail markup looks like",
            "Where to check a quote before you commit",
        ],
        "cta": "Compare live price-per-carat by shape on ZVDapp",
    },
    {
        "id": "engagement-rings",
        "label": "Engagement & bridal",
        "weight": 5,
        "terms": [
            "engagement ring", "engagement rings", "proposal", "bridal", "wedding band",
            "wedding ring", "solitaire", "halo ring", "she said yes", "bride", "fiance",
            "ring size", "wedding jewelry",
        ],
        "b2b": ["retailer", "inventory", "stock", "wholesale", "category", "sales data"],
        "b2c": ["bride", "proposal", "how much", "which", "style", "budget", "he asked", "she said"],
        "angle": "Build style-led buying pages that answer the exact ring questions asked in forums this week, each ending in a shoppable shortlist.",
        "formats": "Buying guide + style gallery + ring-size tool",
        "hook": "Ring buyers research for weeks and decide in minutes - the winners are the pages that survive the research phase.",
        "outline": [
            "The styles trending this week, with photos and price bands",
            "{kw}, answered directly with examples",
            "Setting types: what each one does to the apparent size of the stone",
            "Budget splits that look expensive and cost less",
            "Timeline: how long a custom ring actually takes",
            "Try-before-you-buy and resize policies",
        ],
        "cta": "Build a ring around a certified centre stone on ZVDapp",
    },
    {
        "id": "grading-certs",
        "label": "Grading & certificates",
        "weight": 4,
        "terms": [
            "gia", "igi", "certification", "certified", "certificate", "grading", "4cs",
            "four cs", "clarity grade", "color grade", "colour grade", "appraisal",
            "diamond report", "lab report", "fluorescence",
        ],
        "b2b": ["lab", "grader", "report volume", "standard", "accreditation", "trade"],
        "b2c": ["should i", "is it worth", "real", "fake", "how to check", "verify"],
        "angle": "Own the trust queries: a plain-English certificate explainer that also shows how to verify any report number in seconds.",
        "formats": "Explainer + verification walkthrough video",
        "hook": "Every buyer eventually asks 'is this real?' - the brand with the clearest answer wins the transaction.",
        "outline": [
            "What a certificate does and does not tell you",
            "Reading {kw} in under two minutes",
            "IGI vs GIA vs in-house: the differences that change price",
            "How to verify a report number before you pay",
            "Five red flags in a listing",
        ],
        "cta": "Every stone on ZVDapp ships with a verifiable report",
    },
    {
        "id": "jewelry-retail",
        "label": "Retail & brands",
        "weight": 4,
        "terms": [
            "jewelry retail", "jewellery retail", "jewelry sales", "jewellery sales", "retailer",
            "jeweller", "jeweler", "jewelry store", "jewellery store", "signet", "tiffany",
            "cartier", "pandora", "high street", "footfall", "same-store", "earnings",
            "holiday season", "christmas sales", "valentine",
        ],
        "b2b": ["retailer", "earnings", "revenue", "comparable sales", "store closures",
                "category", "market share", "brand strategy"],
        "b2c": ["store", "shop", "gift", "sale", "collection", "christmas", "valentine"],
        "angle": "Turn brand and retail earnings news into a 'what this means for independent buyers and sellers' column that positions ZVDapp as the marketplace outside the big-box channel.",
        "formats": "Weekly market note + LinkedIn post + newsletter",
        "hook": "Big-box jewellery results are a free, credible news hook for the case that a marketplace beats a mall chain.",
        "outline": [
            "What the brands reported this week",
            "What {kw} signals about where demand is going",
            "Where independent buyers get better value",
            "Gift-season timing: what to launch and when",
            "What ZVDapp sellers should stock next month",
        ],
        "cta": "List or source with ZVDapp instead of a mall chain",
    },
    {
        "id": "wholesale-b2b",
        "label": "Wholesale & trade",
        "weight": 5,
        "terms": [
            "wholesale", "b2b", "trade show", "jck", "vicenzaoro", "hong kong show",
            "bourse", "sightholder", "memo", "tender", "dealer", "supplier", "distributor",
            "bulk order", "trade price", "diamond exchange", "manufacturer", "sourcing",
        ],
        "b2b": ["trade", "dealer", "supplier", "wholesale", "memo", "inventory", "bourse",
                "tender", "manufacturer", "distributor", "B2B"],
        "b2c": [],
        "angle": "Publish trade-facing intelligence: what is moving, at what memo terms, and where the arbitrage is - the content that makes a marketplace the trade's default reference.",
        "formats": "Trade briefing + gated price sheet + LinkedIn carousel",
        "hook": "Trade buyers do not need inspiration, they need terms, spread and availability - publish that and they bookmark you.",
        "outline": [
            "What moved in the trade this week",
            "{kw}: the spread between asking and clearing prices",
            "Memo terms and payment expectations by market",
            "Certificates and parcel breakdowns buyers now expect",
            "Where to source verified parcels on ZVDapp",
        ],
        "cta": "Open a trade account on ZVDapp and see parcel-level pricing",
    },
    {
        "id": "sustainability",
        "label": "Traceability & ethics",
        "weight": 3,
        "terms": [
            "sustainability", "sustainable", "ethical", "conflict free", "conflict-free",
            "kimberley", "traceability", "traceable", "recycled gold", "responsible sourcing",
            "carbon neutral", "human rights", "mining impact", "provenance", "blockchain",
        ],
        "b2b": ["compliance", "regulation", "audit", "supply chain", "ESG", "sanctions",
                "certification scheme", "due diligence"],
        "b2c": ["ethical", "conflict", "should i", "guilt", "sustainable gift"],
        "angle": "Make provenance a product feature: a short, evidence-led page on where ZVDapp stones come from and how a buyer can check.",
        "formats": "Trust page + provenance explainer + short video",
        "hook": "Ethics questions convert better than ethics lectures - show the evidence trail instead of making claims.",
        "outline": [
            "What traceability means in practice for a single stone",
            "{kw}: the claims worth trusting and the ones that are marketing",
            "Regulation changes buyers should know about",
            "How ZVDapp documents provenance",
            "Questions to ask any seller",
        ],
        "cta": "See provenance and certification on every ZVDapp listing",
    },
    {
        "id": "jewelry-trends",
        "label": "Trends & style",
        "weight": 4,
        "terms": [
            "trend", "trends", "red carpet", "celebrity", "engagement ring style", "yellow gold",
            "rose gold", "platinum", "stacking", "men's jewelry", "mens jewelry", "tennis bracelet",
            "stud earrings", "gift guide", "gifting", "fashion", "style", "aesthetic",
        ],
        "b2b": ["forecast", "buying plan", "category growth", "assortment"],
        "b2c": ["gift", "style", "trend", "wear", "outfit", "celebrity", "red carpet"],
        "angle": "Ride the trend cycle with fast, shoppable posts: pick the week's strongest style signal, show three price points, link the category.",
        "formats": "Shoppable edit + Reels/TikTok script + Pinterest set",
        "hook": "Trend content is only commercially useful if a reader can buy the look at three price points in the same scroll.",
        "outline": [
            "The look that is trending this week and why now",
            "{kw}, styled three ways",
            "Entry, mid and statement price points from the marketplace",
            "Metal and stone pairings that photograph well",
            "What to buy now vs wait for",
        ],
        "cta": "Shop the edit on ZVDapp",
    },
    {
        "id": "jewelry-tech",
        "label": "E-commerce & tech",
        "weight": 4,
        "terms": [
            "ecommerce", "e-commerce", "online sales", "online jewellery", "virtual try-on",
            "augmented reality", "3d printing", "tiktok", "instagram", "social commerce",
            "marketplace", "live selling", "ai", "chatgpt", "digital", "app", "platform",
        ],
        "b2b": ["platform", "marketplace", "conversion", "traffic", "CAC", "retention",
                "fulfilment", "AI", "automation", "seller tools"],
        "b2c": ["online", "app", "tiktok", "instagram", "try on", "live"],
        "angle": "Publish operator-grade e-commerce content that doubles as proof ZVDapp is the modern channel: what is working in jewellery online sales this month.",
        "formats": "Operator note + case study + LinkedIn post",
        "hook": "Jewellery is finally buying online the way fashion does - the brands publishing the playbook get the sellers.",
        "outline": [
            "What changed in jewellery e-commerce this week",
            "{kw}: the numbers behind it",
            "The listing elements that move conversion",
            "Live selling and short video: what actually sells stones",
            "How to launch on ZVDapp in a week",
        ],
        "cta": "Apply to sell on ZVDapp",
    },
    {
        "id": "diamond-investment",
        "label": "Investment & resale",
        "weight": 3,
        "terms": [
            "diamond investment", "invest in diamonds", "resale value", "resale", "second hand",
            "second-hand", "auction", "christie's", "sotheby's", "store of value", "asset class",
            "hedge", "appreciate",
        ],
        "b2b": ["auction house", "estate", "liquidity", "secondary market", "valuation"],
        "b2c": ["worth", "resell", "investment", "should i", "lose value"],
        "angle": "Answer the resale question honestly and in detail. The brand that tells buyers when diamonds are a bad investment earns the right to be believed on everything else.",
        "formats": "Honest explainer + FAQ + video",
        "hook": "Nobody trusts a seller who says every stone is an investment - clarity converts.",
        "outline": [
            "When a diamond holds value and when it does not",
            "{kw}, with real numbers",
            "Lab-grown vs natural resale after three years",
            "Auction results as a sanity check",
            "How to buy with exit in mind",
        ],
        "cta": "Compare stones with resale and certificate data on ZVDapp",
    },
]

THEME_BY_ID = {theme["id"]: theme for theme in THEMES}

# Search-intent seeds. Each returns ~10 Google autocomplete suggestions.
AUTOCOMPLETE_SEEDS = [
    "lab grown diamond",
    "lab grown diamond ring",
    "natural diamond",
    "natural vs lab grown diamond",
    "natural diamond engagement ring",
    "diamond price",
    "1 carat diamond",
    "diamond certificate",
    "diamond clarity",
    "engagement ring",
    "engagement ring styles 2026",
    "diamond earrings",
    "diamond necklace",
    "diamond tennis bracelet",
    "diamond wholesale",
    "loose diamond supplier",
    "jewelry wholesale",
    "gia certified diamond",
    "diamond jewelry trend",
    "jewelry trends 2026",
    "moissanite vs diamond",
    "diamond investment",
    "diamond resale value",
    "custom engagement ring",
    "diamond rings for men",
    "diamond pendant",
]

# Google News queries - the "what is the industry talking about" side.
NEWS_QUERIES = [
    '"lab grown diamond" price',
    '"natural diamond" market',
    '"diamond market" demand',
    'diamond jewelry retail sales',
    '"engagement ring" trends',
    'jewelry brand earnings diamond',
    '"De Beers" diamond',
    'diamond trade wholesale bourse',
    'diamond grading GIA IGI',
    'lab grown diamond supply Surat India',
    'jewelry ecommerce online sales growth',
    'diamond traceability sustainability sourcing',
    'TikTok jewelry selling',
    "diamond auction Christie's Sotheby's",
]

# Community signal. Reddit's public Atom feeds need no key and carry the real buyer questions.
# One combined search request covers every relevant subreddit and stays under Reddit's
# aggressive feed rate limit (per-subreddit requests get 429s when fired together).
COMMUNITY_SUBS = "Diamonds+labdiamonds+EngagementRings+jewelry"
COMMUNITY_QUERY = "diamond"

BRAND_TERMS = ["ZVDapp", "ZVD app", "zvdapp.com"]

COMPETITORS = [
    "Brilliant Earth",
    "Blue Nile",
    "James Allen",
    "Rare Carat",
    "Signet Jewelers",
    "Toshakhana",
]

# Buying-stage vocabulary for autocomplete queries.
# Headline used when no search query is strong enough to become the topic title.
FALLBACK_TITLES = {
    "lab-grown": "Lab-grown vs natural: the price and resale comparison",
    "natural-diamond": "What this week's supply news means for diamond buyers",
    "diamond-prices": "Diamond price per carat: this month's benchmark",
    "engagement-rings": "Engagement ring styles buyers are researching this week",
    "grading-certs": "How to read a diamond certificate before you pay",
    "jewelry-retail": "What the big jewellery brands' results mean for independent buyers",
    "wholesale-b2b": "Trade briefing: what is moving at wholesale this week",
    "sustainability": "Where your diamond came from: the provenance page buyers check",
    "jewelry-trends": "The jewellery look trending this week, at three price points",
    "jewelry-tech": "What is actually selling diamonds online this month",
    "diamond-investment": "Do diamonds hold value? An honest answer with numbers",
}

# Retail chains and marketplaces. Queries mentioning them are worth capturing, but they
# are weak headlines for a marketplace's own content, so they are deprioritised.
RETAILER_BRANDS = [
    "costco", "walmart", "sam's club", "sams club", "target", "amazon", "etsy",
    "kay jewelers", "kay jewellers", "zales", "jared", "tiffany", "cartier",
    "pandora", "brilliant earth", "blue nile", "james allen", "rare carat",
    "macy's", "macys", "nordstrom", "mejuri", "overstock",
]

# Autocomplete noise: entertainment, company registrations and trivia rather than buying intent.
NOISE_QUERY_PARTS = [
    "affair", "lyrics", "song", "net worth", "meaning", " llc", " inc", " corp",
    " ltd", "stock price", "ticker", "roblox", "minecraft", "porn", "meme",
    "imdb", "album", "trailer", "cast", "wikipedia", "full movie",
    "dog food", "cat food", "dog name", "baby name", "tattoo", "doorbell",
    "onion ring", "boxing", "fortnite", "pokemon", " bts ", "vape",
]

# A signal must mention one of these to count as diamond-industry relevant.
CORE_TERMS = [
    "diamond", "diamonds", "lab grown", "lab-grown", "lab created", "lab-created",
    "carat", "gia", "igi", "moissanite", "engagement ring", "bridal", "solitaire",
    "tennis bracelet", "4c", "jewellery", "jewelry",
]

STAGE_RULES = [
    ("Compare", [" vs ", "versus", "or ", "better than", "difference between"]),
    ("Price / commercial", ["price", "cost", "how much", "cheap", "affordable", "budget",
                            "for sale", "buy", "wholesale price", "per carat"]),
    ("Trade", ["wholesale", "supplier", "dealer", "bourse", "bulk", "trade", "memo", "b2b"]),
    ("Research", ["how to", "what is", "why", "guide", "meaning", "explained", "check",
                  "verify", "real or fake"]),
    ("Browse", ["near me", "best", "ideas", "styles", "design", "collection", "gift"]),
]
