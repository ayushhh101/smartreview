"""Aspect lexicon for musical-instrument reviews.

Seed terms are matched against lemmas. Known limits (documented, not hidden):
- Pure keyword matching: "cheap" is left out because it means "low price" or "feels flimsy".
- A term belongs to ONE aspect to keep counts interpretable ("pitch" -> tuning, not sound).
- Hand-built seed list; extend after inspecting top terms from the real data.
"""
ASPECTS = {
    "sound": {"sound", "tone", "volume", "loud", "quiet", "noise", "noisy", "hum", "buzz", "static",
              "distortion", "bass", "treble", "clarity", "audio", "sustain", "reverb", "resonance",
              "crackle", "hiss", "mic", "microphone", "speaker"},
    "build_quality": {"build", "quality", "sturdy", "flimsy", "plastic", "metal", "solid", "material",
                      "construction", "finish", "wobbly", "craftsmanship", "wood"},
    "durability": {"break", "broke", "broken", "durable", "durability", "fail", "wear",
                   "die", "snap", "defect", "defective", "crack", "rust"},
    "price_value": {"price", "value", "cost", "worth", "money", "expensive", "bargain",
                    "overpriced", "afford", "affordable", "deal", "buck"},
    "ease_of_use": {"easy", "setup", "install", "instruction", "manual", "simple", "assemble",
                    "beginner", "learn", "intuitive", "adjust"},
    "playability": {"play", "feel", "action", "fret", "neck", "key", "pedal", "comfortable", "comfort",
                    "grip", "fit", "weight", "heavy", "string", "pick", "bow", "reed"},
    "tuning": {"tune", "tuner", "tuning", "intonation", "pitch", "accurate", "calibrate"},
    "connectivity_power": {"battery", "power", "cable", "cord", "bluetooth", "wireless", "usb", "plug",
                           "adapter", "connect", "connection", "jack", "midi", "charge", "signal", "range"},
    "shipping_packaging": {"ship", "shipping", "package", "packaging", "arrive", "arrived", "delivery",
                           "deliver", "box", "damaged"},
    "customer_service": {"support", "service", "warranty", "return", "refund", "replace", "replacement",
                         "seller", "customer", "exchange"},
}
TERM_TO_ASPECT = {t: a for a, terms in ASPECTS.items() for t in terms}
