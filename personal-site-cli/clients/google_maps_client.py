from typing import Dict, List

import googlemaps as gm


class GoogleMapsClient(object):
    CITIES_TYPE = "(cities)"
    DEFAULT_SEARCH_RADIUS_METERS = 25000

    def __init__(self, api_key: str):
        self._gm: gm.Client = gm.Client(key=api_key)

    def get_destination_suggestions(self, text: str) -> List:
        """
        A method for autocompleting city names given a text entry
        """
        return self._gm.places_autocomplete(text, types=[self.CITIES_TYPE])

    def get_place_suggestions(
        self, text: str, location=None, radius: int = DEFAULT_SEARCH_RADIUS_METERS
    ) -> List:
        """
        A method for autocompleting places given a text entry

        Arguments:
            text <str>: A place name
            location <list>: A list of lat, long coordinates
            radius <str>: The radius (in meters) from location to focus the search on
        """
        res = self._gm.places_autocomplete(text, location=location, radius=radius)
        return res

    def geocode_destination(self, place_id: str) -> Dict:
        """
        A method for retrieving information about a city given its place_id
        """
        s = self._gm.reverse_geocode(place_id)[0]

        for comp in s["address_components"]:
            if "country" in comp["types"]:
                country = comp["long_name"]
                country_code = comp["short_name"]

        data = {
            "name": s["address_components"][0]["long_name"],
            "country": country,
            "country_code": country_code,
            "latitude": s["geometry"]["location"]["lat"],
            "longitude": s["geometry"]["location"]["lng"],
            "place_id": place_id,
        }
        return data

    def geocode_place(self, place_id: str) -> Dict:
        """
        A method for retrieving information about a place given its place_id
        """
        s = self._gm.reverse_geocode(place_id)[0]

        country, zip_code, street, street_number, state = "", "", "", "", ""
        for comp in s["address_components"]:
            if "country" in comp["types"]:
                country = comp["long_name"]
            elif "postal_code" in comp["types"]:
                zip_code = comp["long_name"]
            elif "street_number" in comp["types"]:
                street_number = comp["long_name"]
            elif "route" in comp["types"]:
                street = comp["long_name"]
            elif "administrative_area_level_1" in comp["types"]:
                state = comp["long_name"]

        return {
            "place_id": s["place_id"],
            "address": street + " " + street_number,
            "state": state,
            "country": country,
            "zip_code": zip_code,
            "latitude": s["geometry"]["location"]["lat"],
            "longitude": s["geometry"]["location"]["lng"],
        }
