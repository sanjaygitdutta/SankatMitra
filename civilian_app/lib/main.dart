import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:dio/dio.dart';
import 'firebase_options.dart';
import 'providers/alert_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Start the UI immediately so the user doesn't see a blank screen
  runApp(const SankatMitraCivilianApp());

  // Initialize Firebase in the background
  _initializeFirebase();
}

Future<void> _initializeFirebase() async {
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
    
    // Request notification permission
    final messaging = FirebaseMessaging.instance;
    await messaging.requestPermission(alert: true, badge: true, sound: true);
    
    // Get FCM token for targeting
    final token = await messaging.getToken();
    debugPrint('FCM Token: $token');

    // Setup message handlers
    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    debugPrint('Firebase initialized successfully');
    
    // Start GPS heartbeat for civilians
    _startCivilianGpsHeartbeat();
  } catch (e) {
    debugPrint('Firebase background initialization failed: $e');
  }
}

// Global background handler
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  debugPrint("Handling background message: ${message.messageId}");
}

void _handleForegroundMessage(RemoteMessage message) {
  debugPrint("Foreground message received: ${message.data}");
  // The AlertProvider will automatically hear this via a global state mechanism
  // In this prototype, we'll use a simple static access or event bus
}

void _startCivilianGpsHeartbeat() {
  Geolocator.getPositionStream(
    locationSettings: const LocationSettings(
      accuracy: LocationAccuracy.medium,
      distanceFilter: 20, // metres
    ),
  ).listen((position) async {
    try {
      final dio = Dio(BaseOptions(baseUrl: 'https://api.sankatmitra.in/prod'));
      await dio.post('/gps/update', data: {
        'vehicleId': 'civilian_${position.timestamp.millisecondsSinceEpoch}', // Anonymous
        'type': 'CIVILIAN',
        'coordinate': {
          'latitude': position.latitude,
          'longitude': position.longitude,
          'accuracy': position.accuracy,
          'timestamp': DateTime.now().toIso8601String(),
        },
      });
    } catch (e) {
      debugPrint('GPS heartbeart error: $e');
    }
  });
}

class SankatMitraCivilianApp extends StatelessWidget {
  const SankatMitraCivilianApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AlertProvider()),
      ],
      child: MaterialApp(
        title: 'SankatMitra',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFFFF6F00),
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: const CivilianHomeScreen(),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Civilian Home Screen – full UI with map + alert overlay
// ---------------------------------------------------------------------------

class CivilianHomeScreen extends StatefulWidget {
  const CivilianHomeScreen({super.key});

  @override
  State<CivilianHomeScreen> createState() => _CivilianHomeScreenState();
}

class _CivilianHomeScreenState extends State<CivilianHomeScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.85, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Initialize FCM
    _setupFCM();
  }

  void _setupFCM() {
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      if (!mounted) return;
      final alert = context.read<AlertProvider>();
      alert.handleIncomingAlert(message.data);
    });
    // Background handler is already registered in _initializeFirebase
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alertProv = context.watch<AlertProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFF0F0F1A),
      body: Stack(
        children: [
          // ── Map background ─────────────────────────────────────────────
          const GoogleMap(
            initialCameraPosition: CameraPosition(
              target: LatLng(19.0760, 72.8777),
              zoom: 14,
            ),
            myLocationEnabled: true,
            mapType: MapType.normal,
          ),

          // ── Status bar ─────────────────────────────────────────────────
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.fromLTRB(16, 48, 16, 12),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.black.withValues(alpha: 0.8), Colors.transparent],
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.local_hospital, color: Color(0xFFFF6F00), size: 24),
                  const SizedBox(width: 8),
                  const Text('SankatMitra',
                      style: TextStyle(color: Colors.white, fontSize: 18,
                          fontWeight: FontWeight.bold)),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.settings, color: Colors.white70),
                    onPressed: () => _showSettings(context, alertProv),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: alertProv.hasActiveAlert
                          ? Colors.red.withValues(alpha: 0.8)
                          : Colors.green.withValues(alpha: 0.6),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      alertProv.hasActiveAlert ? '🚨 ALERT ACTIVE' : '✅ Clear',
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // ── Alert overlay ──────────────────────────────────────────────
          if (alertProv.hasActiveAlert && alertProv.showTextAlert)
            _AlertOverlay(
              alert: alertProv.currentAlert!,
              pulseAnimation: _pulseAnimation,
              onDismiss: alertProv.dismissAlert,
            ),
        ],
      ),
    );
  }

  void _showSettings(BuildContext context, AlertProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF16213E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Alert Preferences',
                  style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 24),
              SwitchListTile(
                title: const Text('Voice Instructions', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Sequential EN/HI/BN voice guidance', style: TextStyle(color: Colors.white54)),
                value: provider.playVoiceAlert,
                activeTrackColor: const Color(0xFFFF6F00),
                onChanged: (val) {
                  provider.toggleVoice(val);
                  setState(() {});
                },
              ),
              SwitchListTile(
                title: const Text('Text Notifications', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Show visual alert overlay', style: TextStyle(color: Colors.white54)),
                value: provider.showTextAlert,
                activeTrackColor: const Color(0xFFFF6F00),
                onChanged: (val) {
                  provider.toggleText(val);
                  setState(() {});
                },
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}

// Background logic moved to top-level

// ---------------------------------------------------------------------------
// Alert Overlay Widget
// ---------------------------------------------------------------------------

class _AlertOverlay extends StatefulWidget {
  final Map<String, dynamic> alert;
  final Animation<double> pulseAnimation;
  final VoidCallback onDismiss;

  const _AlertOverlay({
    required this.alert,
    required this.pulseAnimation,
    required this.onDismiss,
  });

  @override
  State<_AlertOverlay> createState() => _AlertOverlayState();
}

class _AlertOverlayState extends State<_AlertOverlay> {
  int _langIndex = 0;
  Timer? _timer;
  Map<String, dynamic> _multilingual = {};

  @override
  void initState() {
    super.initState();
    _parseAlerts();
    _startRotation();
  }

  void _parseAlerts() {
    try {
      if (widget.alert['alerts'] != null) {
        _multilingual = json.decode(widget.alert['alerts']);
      } else {
        _multilingual = {'en': widget.alert['body'] ?? 'Emergency vehicle approaching'};
      }
    } catch (e) {
      _multilingual = {'en': widget.alert['body'] ?? 'Emergency vehicle approaching'};
    }
  }

  void _startRotation() {
    final languages = _multilingual.keys.toList();
    if (languages.length <= 1) return;

    _timer = Timer.periodic(const Duration(seconds: 3), (timer) {
      if (mounted) {
        setState(() {
          _langIndex = (_langIndex + 1) % languages.length;
        });
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  IconData _directionIcon(String direction) {
    switch (direction) {
      case 'LEFT': return Icons.arrow_left;
      case 'RIGHT': return Icons.arrow_right;
      default: return Icons.arrow_downward;
    }
  }

  @override
  Widget build(BuildContext context) {
    final direction = widget.alert['direction'] ?? 'PULL_OVER';
    final eta = widget.alert['etaSeconds'] ?? '120';
    final languages = _multilingual.keys.toList();
    final currentText = _multilingual[languages[_langIndex]] ?? '';

    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: AnimatedBuilder(
        animation: widget.pulseAnimation,
        builder: (_, child) => Transform.scale(scale: widget.pulseAnimation.value, child: child),
        child: Container(
          margin: const EdgeInsets.all(16),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFFB71C1C),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.red.withValues(alpha: 0.5),
                blurRadius: 20,
                spreadRadius: 4,
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const Icon(Icons.local_hospital, color: Colors.white, size: 32),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('🚑 AMBULANCE APPROACHING',
                            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                        Text('Arriving in ~$eta seconds', style: const TextStyle(color: Colors.white70)),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white70),
                    onPressed: widget.onDismiss,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(_directionIcon(direction), color: Colors.white, size: 48),
                  const SizedBox(width: 8),
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 500),
                      child: Text(
                        currentText.toUpperCase(),
                        key: ValueKey(currentText),
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
