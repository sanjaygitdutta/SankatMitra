import 'dart:async';
import 'dart:convert';
import 'dart:math' show sin, cos, sqrt, atan2, pi;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'firebase_options.dart';
import 'providers/alert_provider.dart';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const String _apiBase = 'https://r0bh4n62b6.execute-api.ap-south-1.amazonaws.com/prod';
const double _proximityThresholdMeters = 500.0;
const Duration _pollInterval = Duration(seconds: 5);

// ---------------------------------------------------------------------------
// Haversine distance
// ---------------------------------------------------------------------------
double _haversineMeters(double lat1, double lon1, double lat2, double lon2) {
  const R = 6371000.0;
  final dLat = (lat2 - lat1) * pi / 180;
  final dLon = (lon2 - lon1) * pi / 180;
  final a = sin(dLat / 2) * sin(dLat / 2) +
      cos(lat1 * pi / 180) * cos(lat2 * pi / 180) *
          sin(dLon / 2) * sin(dLon / 2);
  return R * 2 * atan2(sqrt(a), sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// App entry point
// ---------------------------------------------------------------------------
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SankatMitraCivilianApp());
  _initFirebaseOptional();
}

/// Firebase is optional — if permission is denied or Firebase fails, the app
/// still works via the active corridor polling mechanism.
Future<void> _initFirebaseOptional() async {
  try {
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
    final messaging = FirebaseMessaging.instance;
    final settings = await messaging.requestPermission(alert: true, badge: true, sound: true);
    if (settings.authorizationStatus == AuthorizationStatus.authorized) {
      final token = await messaging.getToken();
      debugPrint('FCM Token: $token');
      FirebaseMessaging.onBackgroundMessage(_bgHandler);
      _startGpsHeartbeat(token);
    } else {
      debugPrint('FCM permission denied – polling mode only');
      _startGpsHeartbeat(null);
    }
  } catch (e) {
    debugPrint('Firebase optional init failed: $e – polling mode only');
    _startGpsHeartbeat(null);
  }
}

@pragma('vm:entry-point')
Future<void> _bgHandler(RemoteMessage msg) async {
  await Firebase.initializeApp();
}

/// Stable civilian ID persisted in browser storage.
Future<String> _getCivilianId() async {
  final prefs = await SharedPreferences.getInstance();
  String? id = prefs.getString('civilian_id');
  if (id == null) {
    id = 'CIV-${DateTime.now().millisecondsSinceEpoch}';
    await prefs.setString('civilian_id', id);
  }
  return id;
}

Future<void> _startGpsHeartbeat(String? fcmToken) async {
  final id = await _getCivilianId();
  final dio = Dio(BaseOptions(baseUrl: '$_apiBase/'));
  Geolocator.getPositionStream(
    locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium, distanceFilter: 20),
  ).listen((pos) async {
    try {
      await dio.post('gps/update', data: {
        'vehicleId': id,
        'type': 'CIVILIAN',
        'fcmToken': fcmToken ?? '',
        'coordinate': {
          'latitude': pos.latitude,
          'longitude': pos.longitude,
          'accuracy': pos.accuracy,
          'timestamp': DateTime.now().toIso8601String(),
        },
        'satelliteCount': 8,
        'signalStrength': -75.0,
      });
    } catch (e) {
      debugPrint('GPS heartbeat err: $e');
    }
  });
}

// ---------------------------------------------------------------------------
// Root Widget
// ---------------------------------------------------------------------------
class SankatMitraCivilianApp extends StatelessWidget {
  const SankatMitraCivilianApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [ChangeNotifierProvider(create: (_) => AlertProvider())],
      child: MaterialApp(
        title: 'SankatMitra',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFFFF6F00), brightness: Brightness.dark),
          useMaterial3: true,
        ),
        home: const CivilianHomeScreen(),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Home Screen
// ---------------------------------------------------------------------------
class CivilianHomeScreen extends StatefulWidget {
  const CivilianHomeScreen({super.key});
  @override
  State<CivilianHomeScreen> createState() => _CivilianHomeScreenState();
}

class _CivilianHomeScreenState extends State<CivilianHomeScreen>
    with SingleTickerProviderStateMixin {
  GoogleMapController? _mapController;
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;
  final Set<Marker> _markers = {};
  StreamSubscription<Position>? _posSub;
  Timer? _corridorPollTimer;

  BitmapDescriptor? _carIcon;
  BitmapDescriptor? _ambIcon;
  LatLng? _myPos;
  LatLng? _ambPos;
  String? _activeCorridorId;

  final Dio _dio = Dio(BaseOptions(
    baseUrl: '$_apiBase/',
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(seconds: 5),
  ));

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 800))
      ..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.85, end: 1.0)
        .animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    _loadIcons();
    _startLocationTracking();
    _startCorridorPolling(); // ← PRIMARY: polls every 5s, no FCM needed
  }

  Future<void> _loadIcons() async {
    // ignore: deprecated_member_use
    _carIcon = await BitmapDescriptor.fromAssetImage(
        const ImageConfiguration(size: Size(48, 48)), 'assets/images/car_marker.png');
    // ignore: deprecated_member_use
    _ambIcon = await BitmapDescriptor.fromAssetImage(
        const ImageConfiguration(size: Size(48, 48)), 'assets/images/ambulance_marker.png');
    if (mounted) setState(() {});
  }

  // ── Active Corridor Polling (works without FCM) ──────────────────────────
  void _startCorridorPolling() {
    _corridorPollTimer?.cancel();
    _corridorPollTimer = Timer.periodic(_pollInterval, (_) => _checkActiveCorridor());
    // Also check immediately
    Future.delayed(const Duration(seconds: 2), _checkActiveCorridor);
  }

  Future<void> _checkActiveCorridor() async {
    if (!mounted) return;
    try {
      final resp = await _dio.get('corridor/corridors',
          options: Options(headers: {
            // Public endpoint – no auth token needed
            'Content-Type': 'application/json',
          }));

      final corridors = (resp.data?['corridors'] as List?) ?? [];

      if (corridors.isEmpty) {
        // No active corridors → clear any existing alert
        if (_activeCorridorId != null) _clearAmbulance();
        return;
      }

      for (final c in corridors) {
        final corridorId = c['corridorId'] as String?;
        final status = c['status'] as String? ?? '';
        final ambLatStr = c['ambulanceLat'] as String?;
        final ambLonStr = c['ambulanceLon'] as String?;
        final vehicleId = c['emergencyVehicleId'] as String?;

        // Guards: must be ACTIVE with valid GPS coords
        if (status != 'ACTIVE') continue;
        if (ambLatStr == null || ambLatStr.isEmpty || ambLatStr == 'None') continue;
        if (ambLonStr == null || ambLonStr.isEmpty || ambLonStr == 'None') continue;

        final ambLat = double.tryParse(ambLatStr);
        final ambLon = double.tryParse(ambLonStr);
        if (ambLat == null || ambLon == null) continue;

        // ETA sanity check
        final etaRaw = double.tryParse(c['estimatedDuration']?.toString() ?? '') ?? 0;
        final etaSeconds = etaRaw > 0 ? etaRaw.toInt() : 60; // Default 60s if invalid

        final ambPosition = LatLng(ambLat, ambLon);

        // Check distance – only trigger if within 500m
        if (_myPos != null) {
          final dist = _haversineMeters(
              _myPos!.latitude, _myPos!.longitude, ambLat, ambLon);
          if (dist > _proximityThresholdMeters) {
            if (corridorId == _activeCorridorId) _clearAmbulance();
            continue;
          }
        }

        // Within range → show ambulance marker
        _setAmbulanceMarker(ambPosition);

        // Trigger alert only for new corridor
        if (corridorId != _activeCorridorId) {
          _activeCorridorId = corridorId;
          final alert = context.read<AlertProvider>();
          await alert.handleIncomingAlert({
            'corridorId': corridorId ?? '',
            'ambulanceVehicleId': vehicleId ?? '',
            'direction': 'LEFT',
            'etaSeconds': etaSeconds.toString(),
            'body': 'Emergency vehicle approaching! Move to the left.',
            'alerts': json.encode({
              'en': 'Emergency approaching! Move LEFT now.',
              'hi': 'आपातकालीन वाहन आ रहा है! बाईं ओर मुड़ें।',
              'bn': 'জরুরি গাড়ি আসছে! বাম দিকে সরুন।',
            }),
            'ambulanceLat': ambLatStr,
            'ambulanceLon': ambLonStr,
          });
          if (vehicleId != null) _startAmbulancePosPolling(vehicleId);
        }
        break;
      }
    } catch (e) {
      debugPrint('Corridor poll error: $e');
    }
  }

  // ── Live ambulance position polling ──────────────────────────────────────
  Timer? _ambPollTimer;

  void _startAmbulancePosPolling(String vehicleId) {
    _ambPollTimer?.cancel();
    _ambPollTimer = Timer.periodic(const Duration(seconds: 4), (_) async {
      if (!mounted) return;
      try {
        final resp = await _dio.get('gps/$vehicleId');
        final coord = resp.data?['coordinate'];
        if (coord == null) return;
        final lat = (coord['latitude'] as num?)?.toDouble();
        final lon = (coord['longitude'] as num?)?.toDouble();
        if (lat == null || lon == null) return;
        final newPos = LatLng(lat, lon);

        if (_myPos != null) {
          final dist = _haversineMeters(
              _myPos!.latitude, _myPos!.longitude, lat, lon);
          if (dist > _proximityThresholdMeters) {
            _clearAmbulance();
            return;
          }
        }
        _setAmbulanceMarker(newPos);
      } catch (e) {
        debugPrint('Amb pos poll error: $e');
      }
    });
  }

  void _setAmbulanceMarker(LatLng pos) {
    if (!mounted) return;
    setState(() {
      _ambPos = pos;
      _markers.removeWhere((m) => m.markerId.value == 'ambulance_unit');
      _markers.add(Marker(
        markerId: const MarkerId('ambulance_unit'),
        position: pos,
        icon: _ambIcon ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueRed),
        infoWindow: const InfoWindow(title: '🚑 AMBULANCE'),
      ));
    });
  }

  void _clearAmbulance() {
    if (!mounted) return;
    setState(() {
      _ambPos = null;
      _activeCorridorId = null;
      _markers.removeWhere((m) => m.markerId.value == 'ambulance_unit');
      // Re-add the civilian car immediately using last known position.
      // The GPS stream only fires on movement (distanceFilter: 5m), so without
      // this the car marker disappears until the user physically moves.
      if (_myPos != null) {
        _markers.removeWhere((m) => m.markerId.value == 'user_car');
        _markers.add(Marker(
          markerId: const MarkerId('user_car'),
          position: _myPos!,
          icon: _carIcon ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueBlue),
          infoWindow: const InfoWindow(title: 'MY CAR'),
        ));
      }
    });
    _ambPollTimer?.cancel();
    context.read<AlertProvider>().clearCorridor();
  }

  // ── User GPS Tracking ─────────────────────────────────────────────────────
  void _addCarMarker(LatLng pos) {
    if (!mounted) return;
    setState(() {
      _markers.removeWhere((m) => m.markerId.value == 'user_car');
      _markers.add(Marker(
        markerId: const MarkerId('user_car'),
        position: pos,
        icon: _carIcon ?? BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueBlue),
        infoWindow: const InfoWindow(title: 'MY CAR'),
      ));
    });
  }

  void _startLocationTracking() async {
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.whileInUse || perm == LocationPermission.always) {
      // Get an immediate position so the car marker appears right away
      // (the stream only fires after the user moves distanceFilter meters).
      try {
        final initial = await Geolocator.getCurrentPosition(
            desiredAccuracy: LocationAccuracy.high);
        _myPos = LatLng(initial.latitude, initial.longitude);
        _addCarMarker(_myPos!);
        _mapController?.animateCamera(CameraUpdate.newLatLng(_myPos!));
      } catch (_) {}

      _posSub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
            accuracy: LocationAccuracy.high, distanceFilter: 5),
      ).listen((pos) {
        if (!mounted) return;
        _myPos = LatLng(pos.latitude, pos.longitude);
        _addCarMarker(_myPos!);
        _mapController?.animateCamera(CameraUpdate.newLatLng(_myPos!));
      });
    }
  }

  String _distLabel() {
    if (_myPos == null || _ambPos == null) return '';
    final d = _haversineMeters(_myPos!.latitude, _myPos!.longitude,
        _ambPos!.latitude, _ambPos!.longitude);
    return d < 1000 ? '${d.toStringAsFixed(0)}m' : '${(d / 1000).toStringAsFixed(1)}km';
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _posSub?.cancel();
    _corridorPollTimer?.cancel();
    _ambPollTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alert = context.watch<AlertProvider>();
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F1A),
      body: Stack(children: [
        GoogleMap(
          initialCameraPosition: const CameraPosition(target: LatLng(19.0760, 72.8777), zoom: 14),
          onMapCreated: (c) => _mapController = c,
          markers: Set.from(_markers),
          myLocationEnabled: true,
          myLocationButtonEnabled: false,
          mapType: MapType.normal,
        ),

        // ── Top bar ────────────────────────────────────────────────────────
        Positioned(
          top: 0, left: 0, right: 0,
          child: Container(
            padding: const EdgeInsets.fromLTRB(16, 48, 16, 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter, end: Alignment.bottomCenter,
                colors: [Colors.black.withValues(alpha: 0.85), Colors.transparent],
              ),
            ),
            child: Row(children: [
              const Icon(Icons.local_hospital, color: Color(0xFFFF6F00), size: 24),
              const SizedBox(width: 8),
              const Text('SankatMitra',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              const Spacer(),
              if (alert.hasActiveAlert && _ambPos != null)
                Container(
                  margin: const EdgeInsets.only(right: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                      color: Colors.orangeAccent.withValues(alpha: 0.85),
                      borderRadius: BorderRadius.circular(20)),
                  child: Text('🚑 ${_distLabel()} away',
                      style: const TextStyle(color: Colors.white, fontSize: 12,
                          fontWeight: FontWeight.bold)),
                ),
              IconButton(
                icon: const Icon(Icons.settings, color: Colors.white70),
                onPressed: () => _showSettings(context, alert),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: alert.hasActiveAlert
                      ? Colors.red.withValues(alpha: 0.8)
                      : Colors.green.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(alert.hasActiveAlert ? '🚨 ALERT' : '✅ Clear',
                    style: const TextStyle(color: Colors.white, fontSize: 12)),
              ),
            ]),
          ),
        ),

        // ── Locate Me FAB ─────────────────────────────────────────────────
        Positioned(
          bottom: alert.hasActiveAlert ? 220 : 30, right: 16,
          child: FloatingActionButton(
            heroTag: 'locate_me',
            mini: true,
            backgroundColor: const Color(0xFF16213E),
            child: const Icon(Icons.my_location, color: Color(0xFFFF6F00)),
            onPressed: () {
              if (_myPos != null) {
                _mapController?.animateCamera(CameraUpdate.newLatLngZoom(_myPos!, 15));
              }
            },
          ),
        ),

        // ── Alert overlay ─────────────────────────────────────────────────
        if (alert.hasActiveAlert && alert.showTextAlert)
          _AlertOverlay(
            alert: alert.currentAlert!,
            pulseAnimation: _pulseAnim,
            onDismiss: alert.dismissAlert,
          ),
      ]),
    );
  }

  void _showSettings(BuildContext ctx, AlertProvider prov) {
    showModalBottomSheet(
      context: ctx,
      backgroundColor: const Color(0xFF16213E),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => StatefulBuilder(
        builder: (_, ss) => Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text('Alert Preferences',
                style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            SwitchListTile(
              title: const Text('Voice Instructions', style: TextStyle(color: Colors.white)),
              subtitle: const Text('EN / हिन्दी / বাংলা', style: TextStyle(color: Colors.white54)),
              value: prov.playVoiceAlert,
              activeTrackColor: const Color(0xFFFF6F00),
              onChanged: (v) { prov.toggleVoice(v); ss(() {}); },
            ),
            SwitchListTile(
              title: const Text('Text Overlay', style: TextStyle(color: Colors.white)),
              value: prov.showTextAlert,
              activeTrackColor: const Color(0xFFFF6F00),
              onChanged: (v) { prov.toggleText(v); ss(() {}); },
            ),
            const SizedBox(height: 16),
          ]),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Alert Overlay Widget
// ---------------------------------------------------------------------------
class _AlertOverlay extends StatefulWidget {
  final Map<String, dynamic> alert;
  final Animation<double> pulseAnimation;
  final VoidCallback onDismiss;

  const _AlertOverlay({required this.alert, required this.pulseAnimation, required this.onDismiss});

  @override
  State<_AlertOverlay> createState() => _AlertOverlayState();
}

class _AlertOverlayState extends State<_AlertOverlay> {
  int _langIdx = 0;
  Timer? _rotTimer;
  Map<String, dynamic> _ml = {};

  static const _langFlags = {'en': '🇬🇧', 'hi': '🇮🇳', 'bn': '🇧🇩'};

  @override
  void initState() {
    super.initState();
    _parse();
    _startRotation();
  }

  void _parse() {
    try {
      _ml = widget.alert['alerts'] != null
          ? json.decode(widget.alert['alerts'])
          : {'en': widget.alert['body'] ?? 'Emergency vehicle approaching'};
    } catch (_) {
      _ml = {'en': 'Emergency vehicle approaching'};
    }
  }

  void _startRotation() {
    if (_ml.length <= 1) return;
    _rotTimer = Timer.periodic(const Duration(seconds: 3),
        (_) { if (mounted) setState(() => _langIdx = (_langIdx + 1) % _ml.length); });
  }

  @override
  void dispose() { _rotTimer?.cancel(); super.dispose(); }

  IconData _icon(String dir) {
    switch (dir) {
      case 'LEFT': return Icons.turn_left;
      case 'RIGHT': return Icons.turn_right;
      default: return Icons.arrow_circle_down;
    }
  }

  @override
  Widget build(BuildContext context) {
    final direction = widget.alert['direction'] ?? 'LEFT';
    final eta = widget.alert['etaSeconds'] ?? '120';
    final langs = _ml.keys.toList();
    final lang = langs[_langIdx];
    final text = _ml[lang] ?? '';

    return Positioned(
      bottom: 0, left: 0, right: 0,
      child: AnimatedBuilder(
        animation: widget.pulseAnimation,
        builder: (_, child) => Transform.scale(scale: widget.pulseAnimation.value, child: child),
        child: Container(
          margin: const EdgeInsets.all(16),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
                colors: [Color(0xFFB71C1C), Color(0xFF7F0000)],
                begin: Alignment.topLeft, end: Alignment.bottomRight),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [BoxShadow(color: Colors.red.withValues(alpha: 0.55), blurRadius: 24, spreadRadius: 4)],
          ),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Row(children: [
              const Text('🚑', style: TextStyle(fontSize: 30)),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('AMBULANCE APPROACHING',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15)),
                Text('ETA ~$eta seconds', style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ])),
              IconButton(icon: const Icon(Icons.close, color: Colors.white70), onPressed: widget.onDismiss),
            ]),
            const Divider(color: Colors.white24, height: 20),
            Row(children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12)),
                child: Icon(_icon(direction), color: Colors.white, size: 40),
              ),
              const SizedBox(width: 16),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${_langFlags[lang] ?? ''} ${lang.toUpperCase()}',
                    style: const TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 4),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 400),
                  child: Text(text,
                      key: ValueKey(text),
                      style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.bold)),
                ),
              ])),
            ]),
          ]),
        ),
      ),
    );
  }
}
