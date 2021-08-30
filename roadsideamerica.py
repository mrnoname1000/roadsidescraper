#!/usr/bin/env python3
import sys, re, argparse, textwrap, random, os.path
from pathlib import Path

import requests, pyjsparser, gpxpy
from bs4 import BeautifulSoup
from tqdm import tqdm


# fmt: off
REGIONS = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VT", "VA", "WA", "WV", "WI", "WY", "XAB", "XBC", "XMB",
    "XNB", "XNF", "XNT", "XNS", "XON", "XPQ", "XPE", "XSK", "XYT",
]
# fmt: on
_ARG_REGIONS = ["ALL", *REGIONS]


# strip leading, trailing, and left-hand whitespace
def tristrip(string):
    return textwrap.dedent(string).strip()


def create_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="-",
        help="File to write gpx data to",
    )

    def strupper(s):
        return str(s).upper()

    parser.add_argument(
        "regions",
        metavar="REGION",
        type=strupper,
        nargs="*",
        choices=_ARG_REGIONS,
        default="ALL",
        help="Regions to extract data for",
    )

    return parser


def get_regions():
    resp = requests.get("https://www.roadsideamerica.com")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, features="html.parser")
    options = soup.select("div.tools.group form select option[value]")

    regions = []
    for option in options:
        value = option.get("value")
        basename = os.path.basename(value)
        if basename and basename != "location":
            regions.append(basename.upper())

    return regions


def parse_marker(marker):
    pin = {
        "uid": marker[0],
        "longitude": marker[2],
        "latitude": marker[3],
        "name": marker[4],
    }

    for k in pin:
        pin[k] = pin[k]["value"]

    return pin


def get_call(obj, name):
    if isinstance(obj, dict):
        if obj["type"] == "CallExpression" and obj["callee"]["name"] == name:
            yield parse_marker(obj["arguments"])

        else:
            for x in obj.values():
                yield from get_call(x, name)

    elif isinstance(obj, list):
        for x in obj:
            yield from get_call(x, name)


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.regions == "ALL":
        regions = REGIONS
    else:
        regions = args.regions

        for region in regions:
            if region not in _ARG_REGIONS:
                parser.error(f"Invalid region: {region}")

        if "ALL" in regions:
            regions = REGIONS

    if len(regions) > 1:
        regions = tqdm(regions)

    pins = []
    for region in regions:
        resp = requests.get(
            "https://www.roadsideamerica.com/map/attractionsByState.php",
            params={"state": region},
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, features="html.parser")
        scripts = soup.find_all("script")
        for script in scripts[::-1]:
            if script.get("type") == "text/javascript":
                # TODO: detect correct script by parsing
                js = script.string
                break

        if js is None:
            raise TypeError("No js scripts found")

        parsed = pyjsparser.parse(js)
        # expressions = parsed["body"][0]["body"]

        for marker in get_call(parsed, "addMarkerById"):
            pins.append(marker)
    print(f"{len(pins)} pins extracted", file=sys.stderr)

    # write parsed output
    gpx = gpxpy.gpx.GPX()

    for pin in pins:
        wps = gpxpy.gpx.GPXWaypoint()
        wps.longitude = pin["longitude"]
        wps.latitude = pin["latitude"]
        wps.name = pin["name"]
        wps.description = tristrip(
            f"""
                https://www.roadsideamerica.com/tip/{pin['uid']}
            """
        )

        gpx.waypoints.append(wps)

    xml = gpx.to_xml()

    if str(args.output) == "-":
        sys.stdout.write(xml)
    else:
        args.output.write_text(xml)


if __name__ == "__main__":
    main()
