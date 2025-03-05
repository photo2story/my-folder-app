// /my_flutter_app/lib/services/file_explorer_service.dart

import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:flutter/material.dart';
import '../models/project_model.dart';
import 'api_service.dart';

class FileNode {
  final String path;
  final String label;
  final bool isDirectory;
  final DateTime? lastModified;
  List<FileNode>? children;

  FileNode({
    required this.path,
    required this.label,
    required this.isDirectory,
    this.lastModified,
    this.children,
  });

  factory FileNode.fromJson(Map<String, dynamic> json) {
    return FileNode(
      path: json['path'] as String,
      label: json['label'] as String,
      isDirectory: json['isDirectory'] as bool,
      lastModified: json['lastModified'] != null
          ? DateTime.parse(json['lastModified'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'path': path,
      'label': label,
      'isDirectory': isDirectory,
      'lastModified': lastModified?.toIso8601String(),
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
          path: project.projectId,
          label: project.projectName,
          isDirectory: true,
          lastModified: DateTime.tryParse(project.timestamp),
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