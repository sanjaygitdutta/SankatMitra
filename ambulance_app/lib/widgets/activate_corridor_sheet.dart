import 'package:flutter/material.dart';

class ActivateCorridorSheet extends StatefulWidget {
  final Function(double lat, double lon, String urgency) onActivate;

  const ActivateCorridorSheet({super.key, required this.onActivate});

  @override
  State<ActivateCorridorSheet> createState() => _ActivateCorridorSheetState();
}

class _ActivateCorridorSheetState extends State<ActivateCorridorSheet> {
  final _latController = TextEditingController();
  final _lonController = TextEditingController();
  String _urgency = 'HIGH';

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 24,
        right: 24,
        top: 24,
      ),
      decoration: const BoxDecoration(
        color: Color(0xFF1E1E2E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Activate Emergency Corridor',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _latController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: 'Destination Latitude',
              labelStyle: TextStyle(color: Colors.white70),
              enabledBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: Colors.white24),
              ),
            ),
          ),
          TextField(
            controller: _lonController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: 'Destination Longitude',
              labelStyle: TextStyle(color: Colors.white70),
              enabledBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: Colors.white24),
              ),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Urgency Level',
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
          Row(
            children: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((u) {
              return Expanded(
                child: ChoiceChip(
                  label: Text(u, style: const TextStyle(fontSize: 10)),
                  selected: _urgency == u,
                  onSelected: (val) => setState(() => _urgency = u),
                  selectedColor: const Color(0xFFE53935),
                  backgroundColor: Colors.white10,
                  labelStyle: TextStyle(
                    color: _urgency == u ? Colors.white : Colors.white70,
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 32),
          ElevatedButton(
            onPressed: () {
              final lat = double.tryParse(_latController.text);
              final lon = double.tryParse(_lonController.text);
              if (lat != null && lon != null) {
                widget.onActivate(lat, lon, _urgency);
                Navigator.pop(context);
              }
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFE53935),
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: const Text(
              'ACTIVATE CORRIDOR',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.2,
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
