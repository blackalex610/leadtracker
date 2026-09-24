"""Location suggestions for the search form. These are only used to build text
queries ("gyms in Lozenets, Sofia"); any free-text location also works."""

from __future__ import annotations

CITIES: dict[str, list[str]] = {
    "Sofia": [
        "Center", "Lozenets", "Mladost", "Studentski Grad", "Lyulin", "Nadezhda", "Oborishte",
        "Sredets", "Iztok", "Izgrev", "Geo Milev", "Hadzhi Dimitar", "Druzhba", "Poduyane",
        "Krasno Selo", "Krastova Vada", "Manastirski Livadi", "Borovo", "Ovcha Kupel", "Banishora",
        "Slatina", "Gotse Delchev", "Hipodruma", "Lagera", "Ivan Vazov", "Strelbishte", "Boyana",
        "Dragalevtsi", "Simeonovo", "Vitosha", "Musagenitsa", "Dianabad", "Yavorov", "Serdika",
        "Vrabnitsa", "Obelya", "Knyazhevo", "Pavlovo", "Bankya",
    ],
    "Plovdiv": [
        "Center", "Kapana", "Trakia", "Kamenitsa", "Karshiyaka", "Kyuchuk Parizh", "Mladezhki Halm",
        "Smirnenski", "Izgrev", "Ostromila", "Proslav", "Belomorski",
    ],
    "Varna": [
        "Center", "Chaika", "Levski", "Mladost", "Vladislav Varnenchik", "Asparuhovo", "Briz",
        "Vinitsa", "Galata", "Trakata", "Pobeda", "Kaisieva Gradina", "Vazrazhdane", "Troshevo",
    ],
    "Burgas": [
        "Center", "Lazur", "Slaveykov", "Izgrev", "Meden Rudnik", "Zornitsa", "Bratya Miladinovi",
        "Vazrazhdane", "Sarafovo", "Pobeda", "Kraimorie",
    ],
    "Ruse": [],
    "Stara Zagora": [],
    "Pleven": [],
    "Sliven": [],
    "Dobrich": [],
    "Shumen": [],
    "Pernik": [],
    "Haskovo": [],
    "Yambol": [],
    "Pazardzhik": [],
    "Blagoevgrad": [],
    "Veliko Tarnovo": [],
    "Vratsa": [],
    "Gabrovo": [],
    "Asenovgrad": [],
    "Kazanlak": [],
    "Kyustendil": [],
    "Bansko": [],
}  # fmt: skip

CATEGORY_SUGGESTIONS: list[str] = [
    "gyms", "personal trainers", "beauty salons", "nail salons", "hair salons", "barbers",
    "restaurants", "cafes", "car detailing", "dentists", "physiotherapists",
    "real estate agencies", "massage", "yoga studios", "spas", "veterinarians", "florists",
    "bakeries", "car repair", "photographers", "wedding venues", "tattoo studios",
]  # fmt: skip
