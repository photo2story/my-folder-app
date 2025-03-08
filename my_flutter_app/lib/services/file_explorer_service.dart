// /my_flutter_app/lib/services/file_explorer_service.dart

import 'package:flutter/material.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;
import 'api_service.dart';

class FileExplorerService extends ChangeNotifier {
  final ApiService _apiService;
  List<model.FileNode>? _rootNodes;
  bool _isLoading = false;
  String? _error;

  FileExplorerService({required ApiService apiService}) : _apiService = apiService;

  List<model.FileNode>? get rootNodes => _rootNodes;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadRootDirectory() async {
    try {
      _isLoading = true;
      _error = null;
      notifyListeners();

      final projects = await _apiService.fetchProjects();
      _rootNodes = projects.map((project) {
        return model.FileNode(
          name: project.projectName,
          path: project.projectId,
          isDirectory: true,
        );
      }).toList();

      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> loadChildren(model.FileNode node) async {
    if (!node.isDirectory) return;

    try {
      final children = await _apiService.fetchDirectoryContents(node.path);
      node.children = children.cast<model.FileNode>();
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
      rethrow;
    }
  }
}