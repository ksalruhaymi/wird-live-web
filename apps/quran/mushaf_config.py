# apps/quran/mushaf_config.py

DEFAULT_MUSHAF_KEY = "hafs"

TOTAL_PAGES = 604
QURAN_START_IMAGE = 1
QURAN_END_IMAGE = 604

MUSHAF_DIMENSIONS = {
    "normal": {
        "page_width": 430,
        "page_height": 660,
        "min_width": 350,
        "max_width": 1000,
        "min_height": 400,
        "max_height": 1200,
    },
    "fullscreen": {
        "width_vw": 100,
        "height_ratio": 1.30,
        "max_width_vw": 100,
        "max_height_vh": 100,
    },
}

MUSHAFS = {
    "hafs": {
        "title_key": "mushaf_hafs",
        "image_prefix": "mushaf/hafs/",
    },
    "warsh": {
        "title_key": "mushaf_warsh",
        "image_prefix": "mushaf/warsh/",
    },
    "qaloun": {
        "title_key": "mushaf_qaloun",
        "image_prefix": "mushaf/qaloun/",
    },
    "douri": {
        "title_key": "mushaf_douri",
        "image_prefix": "mushaf/douri/",
    },
    "shuba": {
        "title_key": "mushaf_shuba",
        "image_prefix": "mushaf/shuba/",
    },
    "sousi": {
        "title_key": "mushaf_sousi",
        "image_prefix": "mushaf/sousi/",
    },
}


def get_normal_mushaf_dimensions():
    return MUSHAF_DIMENSIONS["normal"].copy()


def get_fullscreen_mushaf_dimensions():
    return MUSHAF_DIMENSIONS["fullscreen"].copy()


def get_all_mushaf_dimensions():
    return {
        "normal": get_normal_mushaf_dimensions(),
        "fullscreen": get_fullscreen_mushaf_dimensions(),
    }


MUSHAF_PAGE_WIDTH = MUSHAF_DIMENSIONS["normal"]["page_width"]
MUSHAF_PAGE_HEIGHT = MUSHAF_DIMENSIONS["normal"]["page_height"]
MUSHAF_MIN_WIDTH = MUSHAF_DIMENSIONS["normal"]["min_width"]
MUSHAF_MAX_WIDTH = MUSHAF_DIMENSIONS["normal"]["max_width"]
MUSHAF_MIN_HEIGHT = MUSHAF_DIMENSIONS["normal"]["min_height"]
MUSHAF_MAX_HEIGHT = MUSHAF_DIMENSIONS["normal"]["max_height"]

MUSHAF_FULLSCREEN_WIDTH_VW = MUSHAF_DIMENSIONS["fullscreen"]["width_vw"]
MUSHAF_FULLSCREEN_HEIGHT_RATIO = MUSHAF_DIMENSIONS["fullscreen"]["height_ratio"]
MUSHAF_FULLSCREEN_MAX_WIDTH_VW = MUSHAF_DIMENSIONS["fullscreen"]["max_width_vw"]
MUSHAF_FULLSCREEN_MAX_HEIGHT_VH = MUSHAF_DIMENSIONS["fullscreen"]["max_height_vh"]