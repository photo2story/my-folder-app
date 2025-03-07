// /my_flutter_app/lib/services/file_explorer_service.dart

import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:flutter/material.dart';
import '../models/project_model.dart';
import 'api_service.dart';

class FileNode {
  final String name;
  final String path;
  final bool isDirectory;
  List<FileNode> children;

  FileNode({
    required this.name,
    required this.path,
    required this.isDirectory,
    this.children = const [],
  });

  factory FileNode.fromJson(Map<String, dynamic> json) {
    return FileNode(
      name: json['name'] as String,
      path: json['path'] as String,
      isDirectory: json['isDirectory'] as bool,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'path': path,
      'isDirectory': isDirectory,
    };
  }
}

class FileExplorerService extends ChangeNotifier {
  final ApiService _apiService;
  List<FileNode>? _rootNodes;
  bool _isLoading = false;
  String? _error;

  FileExplorerService({required ApiService apiService}) : _apiService = apiService;

  List<FileNode>? get rootNodes => _rootNodes;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadRootDirectory() async {
    try {
      _isLoading = true;
      _error = null;
      notifyListeners();

      final projects = await _apiService.fetchProjects();
      _rootNodes = projects.map((project) {
        return FileNode(
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

  Future<void> loadChildren(FileNode node) async {
    if (!node.isDirectory) return;

    try {
      final children = await _apiService.fetchDirectoryContents(node.path);
      node.children = children;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
      rethrow;
    }
  }
}