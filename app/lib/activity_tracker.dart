import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class ActivityTracker {
  // Use 127.0.0.1 for Android Emulator connecting to localhost backend.
  static const String _baseUrl = 'http://127.0.0.1:8000/api/v1';
  static String? _deviceId;

  static Future<String> getDeviceId() async {
    if (_deviceId != null) return _deviceId!;
    
    final prefs = await SharedPreferences.getInstance();
    String? deviceId = prefs.getString('device_id');
    
    if (deviceId == null) {
      deviceId = const Uuid().v4();
      await prefs.setString('device_id', deviceId);
    }
    
    _deviceId = deviceId;
    return deviceId;
  }

  static Future<void> _logAction({
    required String actionType,
    String? queryText,
    int? productId,
  }) async {
    try {
      final deviceId = await getDeviceId();
      final Map<String, dynamic> payload = {
        'device_id': deviceId,
        'action_type': actionType,
      };
      
      if (queryText != null) payload['query_text'] = queryText;
      if (productId != null) payload['product_id'] = productId;

      await http.post(
        Uri.parse('$_baseUrl/activity'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(payload),
      );
    } catch (e) {
      // Fail silently for analytics tracking to not disrupt the user experience
      print('Failed to log activity: $e');
    }
  }

  static Future<void> logSearch(String query) => 
      _logAction(actionType: 'search', queryText: query);
      
  static Future<void> logLens() => 
      _logAction(actionType: 'lens');
      
  static Future<void> logClick(int productId) => 
      _logAction(actionType: 'click', productId: productId);
}
