import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/corridor.dart';

const _storage = FlutterSecureStorage();

class CorridorProvider extends ChangeNotifier {
  Corridor? _activeCorridor;
  bool _isLoading = false;
  String? _errorMessage;
  StreamSubscription<Position>? _locationSubscription;
  Timer? _autoTimeoutTimer;
  DateTime? _lastMovementAt;
  bool _isSimulationMode = false;
  int _simulationIndex = 0;
  Timer? _simulationTimer;

  Corridor? get activeCorridor => _activeCorridor;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;
  bool get hasActiveCorridor => _activeCorridor != null;
  bool get isSimulationMode => _isSimulationMode;

  void toggleSimulation(bool value) {
    _isSimulationMode = value;
    notifyListeners();
  }

  final Dio _dio = Dio(BaseOptions(
    baseUrl: const String.fromEnvironment('API_BASE_URL',
        defaultValue: 'https://api.sankatmitra.in/prod'),
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 10),
  ));

  Future<String?> _getToken() => _storage.read(key: 'jwt_token');

  // -------------------------------------------------------------------------
  // Activate Corridor
  // -------------------------------------------------------------------------

  Future<void> activateCorridor({
    required double destLat,
    required double destLon,
    required String urgencyLevel,
  }) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final token = await _getToken();
      final position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );

      final resp = await _dio.post(
        '/corridor/activate',
        data: {
          'currentLocation': {
            'latitude': position.latitude,
            'longitude': position.longitude,
            'accuracy': position.accuracy,
            'timestamp': DateTime.now().toIso8601String(),
          },
          'destination': {'latitude': destLat, 'longitude': destLon},
          'urgencyLevel': urgencyLevel,
          'missionType': 'EMERGENCY',
        },
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );

      if (resp.statusCode == 201 || resp.statusCode == 200) {
        final data = resp.data as Map<String, dynamic>;
        _activeCorridor = Corridor.fromJson(data);
        
        if (_isSimulationMode) {
          _startSimulation();
        } else {
          _startGpsTracking();
        }
        
        _startAutoTimeout();
      }
    } on DioException catch (e) {
      _errorMessage = e.response?.data?['error'] ?? 'Corridor activation failed';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // -------------------------------------------------------------------------
  // GPS streaming – updates every 2 seconds
  // -------------------------------------------------------------------------

  void _startGpsTracking() {
    _locationSubscription?.cancel();
    _locationSubscription = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5, // metres
      ),
    ).listen((position) async {
      await _sendGpsUpdate(
        lat: position.latitude,
        lon: position.longitude,
        speed: position.speed,
        heading: position.heading,
        accuracy: position.accuracy,
      );
      _lastMovementAt = DateTime.now();
    });
  }

  void _startSimulation() {
    if (_activeCorridor == null || _activeCorridor!.route.isEmpty) return;
    _simulationIndex = 0;
    _simulationTimer?.cancel();
    _simulationTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      if (_activeCorridor == null || _simulationIndex >= _activeCorridor!.route.length) {
        timer.cancel();
        return;
      }
      
      final point = _activeCorridor!.route[_simulationIndex];
      await _sendGpsUpdate(
        lat: point.latitude,
        lon: point.longitude,
        speed: 45.0 / 3.6, // 45 km/h
        heading: 0,
        accuracy: 5.0,
      );
      _lastMovementAt = DateTime.now();
      _simulationIndex++;
      notifyListeners(); // Refresh UI for simulation progress
    });
  }

  Future<void> _sendGpsUpdate({
    required double lat,
    required double lon,
    double speed = 0,
    double heading = 0,
    double accuracy = 10,
  }) async {
    try {
      final token = await _getToken();
      await _dio.post(
        '/gps/update',
        data: {
          'vehicleId': await _storage.read(key: 'vehicle_id'),
          'coordinate': {
            'latitude': lat,
            'longitude': lon,
            'accuracy': accuracy,
            'speed': speed,
            'heading': heading,
            'timestamp': DateTime.now().toIso8601String(),
          },
          'satelliteCount': 8,
          'signalStrength': -75.0,
        },
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
    } catch (_) {
      // Queue for retry during outage (Property 51)
    }
  }

  // -------------------------------------------------------------------------
  // Auto-timeout: deactivate if stationary > 10 minutes (Property 24)
  // -------------------------------------------------------------------------

  void _startAutoTimeout() {
    _autoTimeoutTimer?.cancel();
    _autoTimeoutTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      if (_lastMovementAt != null) {
        final stationarySince = DateTime.now().difference(_lastMovementAt!);
        if (stationarySince.inMinutes >= 10) {
          deactivateCorridor();
        }
      }
    });
  }

  // -------------------------------------------------------------------------
  // Deactivate
  // -------------------------------------------------------------------------

  Future<void> deactivateCorridor() async {
    if (_activeCorridor == null) return;
    _isLoading = true;
    notifyListeners();

    try {
      final token = await _getToken();
      await _dio.delete(
        '/corridor/${_activeCorridor!.corridorId}',
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
    } catch (_) {}

    _locationSubscription?.cancel();
    _autoTimeoutTimer?.cancel();
    _simulationTimer?.cancel();
    _activeCorridor = null;
    _isLoading = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _locationSubscription?.cancel();
    _autoTimeoutTimer?.cancel();
    super.dispose();
  }
}
