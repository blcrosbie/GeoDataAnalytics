import math

def get_bearing(lat1, long1, lat2, long2):
    dLon = (long2 - long1)
    x = math.cos(math.radians(lat2)) * math.sin(math.radians(dLon))
    y = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(dLon))
    brng = np.arctan2(x,y)
    brng = np.degrees(brng)

    return brng

def get_bearing_label(angle):
    label = None
    if angle < 0:
        angle = 360 + angle
    # Caridinal and Ordinal Allowed
    if angle < 22.5 or angle > 337.5:
        label = 'N'
    elif angle >= 22.5 and angle < 67.5:
        label = 'NE'
    elif angle >= 67.5 and angle < 112.5:
        label = 'E'
    elif angle >= 112.5 and angle < 157.5:
        label = 'SE'
    elif angle >= 157.5 and angle < 202.5:
        label = 'S'
    elif angle >= 202.5 and angle < 247.5:
        label = 'SW'
    elif angle >= 247.5 and angle < 292.5:
        label = 'W'
    elif angle >= 292.5 and angle < 337.5:
        label = 'NW'
    else:
        label = 'N'

    return label
    