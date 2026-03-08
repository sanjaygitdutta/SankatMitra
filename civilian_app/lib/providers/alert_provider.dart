import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:js/js.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Declare the JS functions defined in index.html.
// We pass JSON-encoded strings because Dart List<String> does NOT automatically
// convert to a JS array across the @JS() boundary.
@JS('smSpeak')
external void _jsSpeak(String textsJson, String langsJson);

@JS('smCancelSpeech')
external void _jsCancelSpeech();

/// Multilingual alert provider using the browser's Web Speech API.
/// Voice is played via global JS functions smSpeak / smCancelSpeech in index.html.
class AlertProvider extends ChangeNotifier {
  Map<String, dynamic>? _currentAlert;
  bool _hasActiveAlert = false;
  String? _ambulanceVehicleId;

  bool _playVoiceAlert = true;
  bool _showTextAlert = true;

  Map<String, dynamic>? get currentAlert => _currentAlert;
  bool get hasActiveAlert => _hasActiveAlert;
  bool get playVoiceAlert => _playVoiceAlert;
  bool get showTextAlert => _showTextAlert;
  String? get ambulanceVehicleId => _ambulanceVehicleId;

  AlertProvider() {
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    _playVoiceAlert = prefs.getBool('playVoiceAlert') ?? true;
    _showTextAlert = prefs.getBool('showTextAlert') ?? true;
    notifyListeners();
  }

  Future<void> toggleVoice(bool value) async {
    _playVoiceAlert = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('playVoiceAlert', value);
    if (!value) {
      try { _jsCancelSpeech(); } catch (_) {}
    }
    notifyListeners();
  }

  Future<void> toggleText(bool value) async {
    _showTextAlert = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('showTextAlert', value);
    notifyListeners();
  }

  Future<void> handleIncomingAlert(Map<String, dynamic> data) async {
    _currentAlert = data;
    _hasActiveAlert = true;
    _ambulanceVehicleId = data['ambulanceVehicleId'] as String?;
    notifyListeners();

    if (_playVoiceAlert) {
      _speakMultilingualAlert(data);
    }
  }

  void _speakMultilingualAlert(Map<String, dynamic> data) {
    try {
      Map<String, dynamic> multilingual = {};
      if (data['alerts'] != null) {
        multilingual = json.decode(data['alerts']);
      } else {
        multilingual = {'en': data['body'] ?? 'Emergency vehicle approaching'};
      }

      // Build parallel text + lang arrays for the JS function
      final texts = <String>[];
      final langs = <String>[];
      final bcp47Map = {'en': 'en-US', 'hi': 'hi-IN', 'bn': 'bn-IN'};

      for (final entry in multilingual.entries) {
        final text = (entry.value as String? ?? '').trim();
        if (text.isEmpty) continue;
        texts.add(text);
        langs.add(bcp47Map[entry.key] ?? 'en-US');
      }

      if (texts.isNotEmpty) {
        _jsSpeak(json.encode(texts), json.encode(langs));
      }
    } catch (e) {
      debugPrint('smSpeak error: $e');
    }
  }

  void clearCorridor() {
    _currentAlert = null;
    _hasActiveAlert = false;
    _ambulanceVehicleId = null;
    try { _jsCancelSpeech(); } catch (_) {}
    notifyListeners();
  }

  void dismissAlert() {
    _currentAlert = null;
    _hasActiveAlert = false;
    try { _jsCancelSpeech(); } catch (_) {}
    notifyListeners();
  }
}
