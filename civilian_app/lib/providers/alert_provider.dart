import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AlertProvider extends ChangeNotifier {
  final FlutterTts _tts = FlutterTts();
  Map<String, dynamic>? _currentAlert;
  bool _hasActiveAlert = false;
  
  // User Preferences
  bool _playVoiceAlert = true;
  bool _showTextAlert = true;

  Map<String, dynamic>? get currentAlert => _currentAlert;
  bool get hasActiveAlert => _hasActiveAlert;
  bool get playVoiceAlert => _playVoiceAlert;
  bool get showTextAlert => _showTextAlert;

  AlertProvider() {
    _loadPreferences();
    _initTts();
  }

  Future<void> _initTts() async {
    await _tts.setVolume(1.0);
    await _tts.setSpeechRate(0.5);
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
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
    if (!value) await _tts.stop();
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
    notifyListeners();

    if (_playVoiceAlert) {
      await _speakMultilingualAlert(data);
    }
  }

  Future<void> _speakMultilingualAlert(Map<String, dynamic> data) async {
    try {
      Map<String, dynamic> multilingual = {};
      
      // Try to parse the 'alerts' JSON string from FCM data
      if (data['alerts'] != null) {
        multilingual = json.decode(data['alerts']);
      } else {
        // Fallback to the body if no multilingual data
        multilingual = {'en': data['body'] ?? 'Emergency vehicle approaching'};
      }

      // 1. English
      if (multilingual['en'] != null) {
        await _tts.setLanguage("en-US");
        await _tts.speak(multilingual['en']);
        await Future.delayed(const Duration(seconds: 1)); // Small gap
      }

      // 2. Hindi
      if (multilingual['hi'] != null) {
        await _tts.setLanguage("hi-IN");
        await _tts.speak(multilingual['hi']);
        await Future.delayed(const Duration(seconds: 1));
      }

      // 3. Bengali
      if (multilingual['bn'] != null) {
        await _tts.setLanguage("bn-IN");
        await _tts.speak(multilingual['bn']);
      }
    } catch (e) {
      debugPrint("TTS Error: $e");
    }
  }

  void dismissAlert() {
    _currentAlert = null;
    _hasActiveAlert = false;
    _tts.stop();
    notifyListeners();
  }
}
