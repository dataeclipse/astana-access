SOURCE = (
    "SP RK 3.01-101-2013, edition of 9 July 2021, "
    "with orders 45-NK of 5 March 2018 and 46-NK of 1 April 2019"
)

RADIUS_M = {"preschool": 300.0, "school": 500.0}
RADIUS_TOLERANCE = 0.10
TRANSPORT_MINUTES = {"primary": 15, "other": 50}

PRESCHOOL_COVERAGE_TARGET = 0.85
PRESCHOOL_PLACES_PER_1000_NEW_AREAS = 180
PRESCHOOL_PLACES_PER_1000_IN_HOUSING = 100

SCHOOL_PLACES_PER_1000_NEW_AREAS = 180
SCHOOL_SHARE_GRADES_1_9 = 1.0
SCHOOL_SHARE_GRADES_10_11 = 0.75

SCHOOL_LAND_M2_PER_PUPIL = ((300, 43.0), (600, 34.0), (900, 23.0), (1200, 19.0))
PRESCHOOL_LAND_M2_PER_PLACE = ((100, 40.0), (500, 35.0), (10_000, 30.0))

COMFORTABLE_SCHOOL_SEATS = 2000
SHIFTS = 2


def school_land_m2(pupils: int) -> float:
    for limit, per_pupil in SCHOOL_LAND_M2_PER_PUPIL:
        if pupils <= limit:
            return pupils * per_pupil
    return pupils * SCHOOL_LAND_M2_PER_PUPIL[-1][1]


def preschool_land_m2(places: int) -> float:
    for limit, per_place in PRESCHOOL_LAND_M2_PER_PLACE:
        if places <= limit:
            return places * per_place
    return places * PRESCHOOL_LAND_M2_PER_PLACE[-1][1]
