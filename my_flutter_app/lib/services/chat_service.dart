// /my_flutter_app/lib/services/chat_service.dart


import 'package:flutter/foundation.dart';
import 'package:hive_flutter/hive_flutter.dart';

class ChatService with ChangeNotifier {
  final Box _chatBox = Hive.box('chatBox');
  String? _currentProjectId;

  String? get currentProjectId => _currentProjectId;

  List<String> get messages => _chatBox.get(_currentProjectId ?? '', defaultValue: <String>[]).cast<String>();

  void setProjectId(String projectId) {
    _currentProjectId = projectId;
    notifyListeners();
    print('[DEBUG] ChatService: Project ID set to $projectId');
  }

  void addMessage(String message) {
    if (_currentProjectId == null) return;
    final messages = List<String>.from(_chatBox.get(_currentProjectId!, defaultValue: <String>[]).cast<String>());
    messages.add(message);
    _chatBox.put(_currentProjectId!, messages);
    notifyListeners();
    print('[DEBUG] ChatService: Message added for $_currentProjectId: $message');
  }

  void clearMessages() {
    if (_currentProjectId == null) return;
    _chatBox.put(_currentProjectId!, <String>[]);
    notifyListeners();
    print('[DEBUG] ChatService: Messages cleared for $_currentProjectId');
  }
}