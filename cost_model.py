class CostModel:
    def __init__(self, 
                 bus_daily_cost=200, 
                 van_daily_cost=120, 
                 driver_hourly_rate=25,
                 hours_per_trip=1):
        self.bus_cost = bus_daily_cost
        self.van_cost = van_daily_cost
        self.driver_rate = driver_hourly_rate
        self.hours = hours_per_trip  # Per vehicle

    def estimate(self, num_buses, num_vans):
        vehicle_cost = num_buses * self.bus_cost + num_vans * self.van_cost
        driver_cost = (num_buses + num_vans) * self.driver_rate * self.hours
        return vehicle_cost + driver_cost
