from langgraph.graph import StateGraph, END
import requests
from datetime import datetime, timedelta
import os

def place(place_name, api_key):
    url = f"https://api.tomtom.com/search/2/geocode/{place_name}.json"
    params = {"key": api_key}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            pos = results[0]["position"]
            print(f"Coordinates '{place_name}' to {pos['lat']}, {pos['lon']}")
            return {"lat": pos["lat"], "lon": pos["lon"]}
    return {"error": f"Failed to get coordinates for '{place_name}'"}

def start(state):
    coords = place(state["start_place"], state["api_key"])
    return {**state, "start_coords": coords}

def end(state):
    coords = place(state["end_place"], state["api_key"])
    return {**state, "end_coords": coords}

def fetch(state):
    start = state["start_coords"]
    end = state["end_coords"]
    api_key = state["api_key"]

    if "error" in start or "error" in end:
        return {**state, "route_data": {"error": "Invalid start or end location"}}

    print(f"Fetching route between {start} -> {end}")

    url = f"https://api.tomtom.com/routing/1/calculateRoute/{start['lat']},{start['lon']}:{end['lat']},{end['lon']}/json"
    params = {
        "key": api_key,
        "traffic": "true",
        "maxAlternatives": 3,
        "instructionsType": "text",
        "routeType": "fastest",
        "travelMode": "car",
        "computeTravelTimeFor": "all"
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return {**state, "route_data": response.json()}
    else:
        print(f"API error: {response.text}")
        return {**state, "route_data": {"error": "Failed to fetch route"}}

def get_place_name(lat, lon, api_key):
    url = f"https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json"
    params = {"key": api_key}
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            address = results[0].get("address", {})
            return address.get("municipality", "Unknown place")
    return "Unknown place"

def analyze_traffic(route_data, api_key):
    routes = route_data.get("routes", [])
    if not routes:
        return "No routes found"

    best_route = routes[0]
    summary = best_route.get("summary", {})
    no_traffic = summary.get("noTrafficTravelTimeInSeconds")
    traffic = summary.get("travelTimeInSeconds")

    if traffic is None or no_traffic is None:
        return "Traffic data unavailable"

    delay = traffic - no_traffic
    result = [f"Time delay due to traffic: {round(delay / 60, 2)} minutes"]

    if delay < 60:
        result.append("No significant congestion along the route.")
        return "\n".join(result)

    sections = best_route.get("sections", [])
    congestion_sections = [s for s in sections if s.get("sectionType") == "TRAFFIC"]

    if not congestion_sections:
        result.append("No major traffic congestion")
    else:
        result.append(f"{len(congestion_sections)} congestion section(s) found:")
        for i, section in enumerate(congestion_sections, 1):
            start_idx = section.get("startPointIndex")
            end_idx = section.get("endPointIndex")

            start_point = best_route["points"][start_idx]
            end_point = best_route["points"][end_idx]

            start_place = get_place_name(start_point[0], start_point[1], api_key)
            end_place = get_place_name(end_point[0], end_point[1], api_key)

            result.append(f"  • Section {i}: Traffic between {start_place} → {end_place}.")

    return "\n".join(result)

def summary(state):
    data = state["route_data"]
    if "error" in data:
        return {**state, "summary": data["error"]}

    try:
        routes = data.get("routes", [])
        if not routes:
            return {**state, "summary": "No routes found"}

        summary_text = "\nSuggested Routes:\n"
        for i, route in enumerate(routes):
            summary_data = route.get("summary", {})
            distance = round(summary_data.get("lengthInMeters", 0) / 1000, 2)
            duration = round(summary_data.get("travelTimeInSeconds", 0) / 60, 2)
            summary_text += f"Route {i+1}: {distance} km, {duration} mins\n"

            if i == 0:
                instructions = route.get("guidance", {}).get("instructions", [])
                summary_text += "\nTop Directions:\n"
                for instr in instructions[:10]:
                    message = instr.get("message", "")
                    if message:
                        summary_text += f"  • {message}\n"

        best_route = min(routes, key=lambda r: r.get("summary", {}).get("travelTimeInSeconds", float("inf")))
        travel_time = best_route.get("summary", {}).get("travelTimeInSeconds")

        summary_text += "\nRoute Suggestion:\n"
        if travel_time is not None:
            eta = datetime.now().replace(second=0, microsecond=0) + timedelta(seconds=travel_time)
            summary_text += f"Estimated time of arrival: {eta.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            summary_text += "Estimated time not available.\n"

        summary_text += "\nTraffic Analysis:\n"
        summary_text += analyze_traffic(data, state["api_key"])

        return {**state, "summary": summary_text}

    except Exception as e:
        return {**state, "summary": f"Failed to summarize route. Error: {str(e)}"}

graph = StateGraph(dict)
graph.add_node("Start", start)
graph.add_node("End", end)
graph.add_node("Fetch_Route", fetch)
graph.add_node("Summary", summary)

graph.set_entry_point("Start")
graph.add_edge("Start", "End")
graph.add_edge("End", "Fetch_Route")
graph.add_edge("Fetch_Route", "Summary")
graph.add_edge("Summary", END)

app = graph.compile()

if __name__ == "__main__":
    print("Real-Time Route Suggestion:\n")
    start_place = input("Enter Departure Place: ")
    end_place = input("Enter Destination Place: ")

    api_key = os.getenv("TOMTOM_API_KEY", "oTAa4xpFZoxGCF8BifBq1o5xlFo9XNCN")  # Replace with your TomTom API key

    inputs = {
        "start_place": start_place,
        "end_place": end_place,
        "api_key": api_key
    }

    final_state = app.invoke(inputs)
    print(f"\nRoute Summary:\n{final_state['summary']}")
