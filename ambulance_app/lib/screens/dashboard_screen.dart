import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';
import '../providers/corridor_provider.dart';
import '../providers/auth_provider.dart';
import '../widgets/corridor_info_card.dart';
import '../widgets/activate_corridor_sheet.dart';
import '../widgets/offline_banner.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  // ignore: unused_field
  GoogleMapController? _mapController;

  @override
  Widget build(BuildContext context) {
    final corridorProv = context.watch<CorridorProvider>();
    final authProv = context.watch<AuthProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: Row(
          children: [
            Image.asset('assets/images/logo.png', height: 32, errorBuilder: (_, __, ___) =>
                const Icon(Icons.local_hospital, color: Color(0xFFE53935), size: 32)),
            const SizedBox(width: 8),
            const Text('SankatMitra',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          // Offline indicator
          if (!authProv.isOnline)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Icon(Icons.wifi_off, color: Colors.orange),
            ),
          // Simulation Toggle
          Row(
            children: [
              const Text('Sim', style: TextStyle(fontSize: 12, color: Colors.white70)),
              Switch(
                value: corridorProv.isSimulationMode,
                activeTrackColor: const Color(0xFFE53935),
                onChanged: (val) => corridorProv.toggleSimulation(val),
              ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.white70),
            onPressed: () {
              authProv.logout();
              Navigator.pushReplacementNamed(context, '/login');
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          // ── Google Map ──────────────────────────────────────────────────
          GoogleMap(
            initialCameraPosition: const CameraPosition(
              target: LatLng(19.0760, 72.8777),
              zoom: 14,
            ),
            onMapCreated: (ctrl) => _mapController = ctrl,
            markers: _buildMarkers(corridorProv),
            polylines: _buildPolylines(corridorProv),
            myLocationEnabled: true,
            myLocationButtonEnabled: true,
            mapType: MapType.normal,
          ),

          // ── Offline banner ──────────────────────────────────────────────
          if (!authProv.isOnline) const OfflineBanner(),

          // ── Loading overlay ─────────────────────────────────────────────
          if (corridorProv.isLoading)
            Container(
              color: Colors.black54,
              child: const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: Color(0xFFE53935)),
                    SizedBox(height: 16),
                    Text('Activating Corridor...',
                        style: TextStyle(color: Colors.white, fontSize: 16)),
                  ],
                ),
              ),
            ),

          // ── Corridor info card (bottom) ─────────────────────────────────
          if (corridorProv.hasActiveCorridor)
            Positioned(
              bottom: 100,
              left: 16,
              right: 16,
              child: CorridorInfoCard(
                corridor: corridorProv.activeCorridor!,
                onCancel: () => corridorProv.deactivateCorridor(),
              ),
            ),

          // ── Error snackbar (via ValueListenableBuilder trick) ───────────
          if (corridorProv.errorMessage != null)
            Positioned(
              bottom: 200,
              left: 16,
              right: 16,
              child: Material(
                color: Colors.red[900],
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(corridorProv.errorMessage!,
                      style: const TextStyle(color: Colors.white)),
                ),
              ),
            ),
        ],
      ),

      // ── FAB: Activate / Deactivate Corridor ─────────────────────────────
      floatingActionButton: corridorProv.hasActiveCorridor
          ? FloatingActionButton.extended(
              backgroundColor: Colors.red[900],
              icon: const Icon(Icons.stop_circle),
              label: const Text('Deactivate Corridor'),
              onPressed: () => corridorProv.deactivateCorridor(),
            )
          : FloatingActionButton.extended(
              backgroundColor: const Color(0xFFE53935),
              icon: const Icon(Icons.emergency),
              label: const Text('Activate Corridor'),
              onPressed: () => showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: const Color(0xFF16213E),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                builder: (_) => ActivateCorridorSheet(
                  onActivate: (lat, lon, urgency) => corridorProv.activateCorridor(
                    destLat: lat,
                    destLon: lon,
                    urgencyLevel: urgency,
                  ),
                ),
              ),
            ),
    );
  } // ← closes build()

  Set<Marker> _buildMarkers(CorridorProvider prov) {
    final markers = <Marker>{};
    if (prov.activeCorridor != null) {
      markers.add(Marker(
        markerId: const MarkerId('destination'),
        position: LatLng(
          prov.activeCorridor!.destination.latitude,
          prov.activeCorridor!.destination.longitude,
        ),
        icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueRed),
        infoWindow: const InfoWindow(title: '🏥 Destination'),
      ));

      // Show current simulated position
      if (prov.isSimulationMode && prov.activeCorridor!.route.isNotEmpty) {
        final idx = (prov.activeCorridor!.route.length - 1)
            .clamp(0, prov.activeCorridor!.route.length - 1);
        final cur = prov.activeCorridor!.route[idx];
        markers.add(Marker(
          markerId: const MarkerId('ambulance'),
          position: LatLng(cur.latitude, cur.longitude),
          icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueOrange),
          infoWindow: const InfoWindow(title: '🚑 Ambulance'),
        ));
      }
    }
    return markers;
  }

  Set<Polyline> _buildPolylines(CorridorProvider prov) {
    if (prov.activeCorridor == null || prov.activeCorridor!.route.isEmpty) {
      return {};
    }
    return {
      Polyline(
        polylineId: const PolylineId('route'),
        points: prov.activeCorridor!.route
            .map((p) => LatLng(p.latitude, p.longitude))
            .toList(),
        color: const Color(0xFFE53935),
        width: 5,
        patterns: [PatternItem.dash(30), PatternItem.gap(10)],
      ),
    };
  }
}
