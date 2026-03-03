class GPSCoordinate {
  final double latitude;
  final double longitude;
  final String? timestamp;
  final double? accuracy;
  final double? speed;
  final double? heading;

  GPSCoordinate({
    required this.latitude,
    required this.longitude,
    this.timestamp,
    this.accuracy,
    this.speed,
    this.heading,
  });

  factory GPSCoordinate.fromJson(Map<String, dynamic> json) {
    return GPSCoordinate(
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      timestamp: json['timestamp'],
      accuracy: (json['accuracy'] as num?)?.toDouble(),
      speed: (json['speed'] as num?)?.toDouble(),
      heading: (json['heading'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'latitude': latitude,
      'longitude': longitude,
      if (timestamp != null) 'timestamp': timestamp,
      if (accuracy != null) 'accuracy': accuracy,
      if (speed != null) 'speed': speed,
      if (heading != null) 'heading': heading,
    };
  }
}

class Corridor {
  final String corridorId;
  final String vehicleId;
  final List<GPSCoordinate> route;
  final GPSCoordinate destination;
  final String status;
  final String? startTime;
  final String urgencyLevel;

  Corridor({
    required this.corridorId,
    required this.vehicleId,
    required this.route,
    required this.destination,
    required this.status,
    this.startTime,
    required this.urgencyLevel,
  });

  factory Corridor.fromJson(Map<String, dynamic> json) {
    return Corridor(
      corridorId: json['corridorId'],
      vehicleId: json['vehicleId'],
      route: (json['route'] as List)
          .map((i) => GPSCoordinate.fromJson(i))
          .toList(),
      destination: GPSCoordinate.fromJson(json['destination']),
      status: json['status'],
      startTime: json['startTime'],
      urgencyLevel: json['urgencyLevel'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'corridorId': corridorId,
      'vehicleId': vehicleId,
      'route': route.map((i) => i.toJson()).toList(),
      'destination': destination.toJson(),
      'status': status,
      if (startTime != null) 'startTime': startTime,
      'urgencyLevel': urgencyLevel,
    };
  }
}
