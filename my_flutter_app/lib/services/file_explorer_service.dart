// /my_flutter_app/lib/services/file_explorer_service.dart

import 'package:flutter/foundation.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;
import 'api_service.dart';

class FileExplorerService with ChangeNotifier {
  final ApiService apiService;
  List<model.FileNode>? rootNodes;
  String? error;
  bool isLoading = false;

  FileExplorerService({required this.apiService});

  Future<void> loadRootDirectory() async {
    isLoading = true;
    notifyListeners();

    try {
      rootNodes = await apiService.fetchDirectoryContents('');
      error = null;
    } catch (e) {
      error = e.toString();
      rootNodes = [];
    }

    isLoading = false;
    notifyListeners();
  }

  Future<void> loadChildren(model.FileNode node) async {
    if (node.children.isNotEmpty) return;

    isLoading = true;
    notifyListeners();

    try {
      final children = await apiService.fetchDirectoryContents(node.path);
      node.children.addAll(children);
      error = null;
    } catch (e) {
      error = e.toString();
    }

    isLoading = false;
    notifyListeners();
  }
}