
def calculate_source_orientation(urls: list) -> dict:
    """
    Calculate the political orientation distribution based on source URLs.
    Returns percentages for each orientation category.
    """
    domain_orientations = {
        "pravda.sk": "center-left",
        "dennikn.sk": "center-left",
        "aktuality.sk": "center",
        "sme.sk": "center",
        "hnonline.sk": "center-right",
        "postoj.sk": "right",
    }

    orientations = {
        "left": 0,
        "center-left": 0,
        "neutral": 0,
        "center-right": 0,
        "right": 0
    }

    total_urls = len(urls)
    if total_urls == 0:
        return {
            "left_percent": 0,
            "center_left_percent": 0,
            "neutral_percent": 100,
            "center_right_percent": 0,
            "right_percent": 0
        }

    for url in urls:
        try:
            domain = url.split("//")[-1].split("/")[0]
            orientation = domain_orientations.get(domain, "neutral")
            orientations[orientation] = orientations.get(orientation, 0) + 1
        except Exception:
            orientations["neutral"] += 1

    return {
        "left_percent": (orientations["left"] / total_urls) * 100,
        "center_left_percent": (orientations["center-left"] / total_urls) * 100,
        "neutral_percent": (orientations["neutral"] / total_urls) * 100,
        "center_right_percent": (orientations["center-right"] / total_urls) * 100,
        "right_percent": (orientations["right"] / total_urls) * 100
    }
