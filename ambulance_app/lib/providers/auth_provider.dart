import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();

class AuthProvider extends ChangeNotifier {
  bool _isAuthenticated = false;
  bool _isOnline = true;
  String? _errorMessage;

  bool get isAuthenticated => _isAuthenticated;
  bool get isOnline => _isOnline;
  String? get errorMessage => _errorMessage;

  final Dio _dio = Dio(BaseOptions(
    baseUrl: const String.fromEnvironment('API_BASE_URL',
        defaultValue: 'https://r0bh4n62b6.execute-api.ap-south-1.amazonaws.com/prod/'),
    connectTimeout: const Duration(seconds: 5),
  ));

  Future<bool> login({
    required String vehicleId,
    required String registrationNumber,
    required String agencyId,
  }) async {
    _errorMessage = null;
    try {
      final resp = await _dio.post('/auth/login', data: {
        'vehicleId': vehicleId,
        'registrationNumber': registrationNumber,
        'agencyId': agencyId,
        'digitalSignature': _generateSignature(vehicleId, registrationNumber),
      });

      if (resp.statusCode == 200) {
        final data = resp.data as Map<String, dynamic>;
        await _storage.write(key: 'jwt_token', value: data['token']);
        await _storage.write(key: 'vehicle_id', value: vehicleId);
        _isAuthenticated = true;
        _isOnline = true;
        notifyListeners();
        return true;
      }
    } on DioException catch (e) {
      _errorMessage = e.response?.data?['errorCode'] ?? 'Authentication failed';
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.connectionError) {
        _isOnline = false;
      }
    }
    notifyListeners();
    return false;
  }

  Future<void> logout() async {
    await _storage.deleteAll();
    _isAuthenticated = false;
    notifyListeners();
  }

  String _generateSignature(String vehicleId, String regNo) {
    // In production: use asymmetric key stored in secure enclave
    return '${vehicleId}_${regNo}_sig';
  }
}
