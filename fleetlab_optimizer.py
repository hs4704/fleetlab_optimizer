class FleetOptimizer:
    def __init__(self, num_students, num_buses, num_vans, cost_model):
        self.num_students = num_students
        self.num_buses = num_buses
        self.num_vans = num_vans
        self.cost_model = cost_model
        self.bus_capacity = 20
        self.van_capacity = 7

    def estimate_cost(self, miles_per_trip, hours_per_trip):
        best = None
        lowest_cost = float("inf")

        for buses in range(self.num_buses + 1):
            for vans in range(self.num_vans + 1):
                capacity = buses * self.bus_capacity + vans * self.van_capacity
                if capacity >= self.num_students:
                    cost = self.cost_model.estimate(buses, vans)
                    if cost < lowest_cost:
                        lowest_cost = cost
                        best = (buses, vans)

        if best is None:
            return {"error": "No valid mix found"}

        return {
            "assigned_buses": best[0],
            "assigned_vans": best[1],
            "total_cost": lowest_cost
        }
