DEFAULT_TOP_IMAGE = "/no_image_press.png"

# Hospodarske noviny, hlavnespravy.sk, trend.sk, noviny.sk, topky.sk, novycas.sk
LANDING_PAGES = [
    {
        "url": "https://pravda.sk/",
        "patterns": ["/clanok/"]
    },
    {
        "url": "https://www.aktuality.sk",
        "patterns": ["/clanok/"]
    },
    {
        "url": "https://domov.sme.sk/",
        "patterns": ["/c/"]
    },
    {
        "url": "https://topky.sk",
        "patterns": ["/cl/"]
    },
    {
        "url": "https://teraz.sk/",
        "patterns": ["/slovensko/","/veda/","/sport/","/zahranicie/","/kultura/","/ekonomika/","/krimi/","/regiony/","/slovensko/","/obce/","/zdravie/"]
    }
]

MEDIA_SOURCES = {
    "pravda.sk": {
        "name": "Pravda",
        "orientation": "center-left",
        "logo": "https://path-to-pravda-logo.svg",
        "domain": "pravda.sk"
    },
    "dennikn.sk": {
        "name": "Denník N",
        "orientation": "center-left",
        "logo": "https://path-to-dennikn-logo.svg",
        "domain": "dennikn.sk"
    },
    "aktuality.sk": {
        "name": "Aktuality",
        "orientation": "neutral",
        "logo": "https://path-to-aktuality-logo.svg",
        "domain": "aktuality.sk"
    },
    "sme.sk": {
        "name": "SME",
        "orientation": "center",
        "logo": "https://path-to-sme-logo.svg",
        "domain": "sme.sk"
    },
    "hnonline.sk": {
        "name": "Hospodárske noviny",
        "orientation": "center-right",
        "logo": "https://path-to-hnonline-logo.svg",
        "domain": "hnonline.sk"
    },
    "postoj.sk": {
        "name": "Postoj",
        "orientation": "right",
        "logo": "https://path-to-postoj-logo.svg",
        "domain": "postoj.sk"
    }
}
