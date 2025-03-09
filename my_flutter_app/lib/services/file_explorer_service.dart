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

  // 프로젝트 노드를 찾아 해당 프로젝트의 모든 문서 노드를 자동으로 확장
  Future<void> expandProjectDocuments(String projectId) async {
    print('[DEBUG] Expanding all documents for project: $projectId');
    
    if (rootNodes == null || rootNodes!.isEmpty) {
      await loadRootDirectory();
    }
    
    // 프로젝트가 속한 부서 노드 찾기
    model.FileNode? departmentNode;
    for (var node in rootNodes ?? []) {
      await loadChildren(node);
      for (var child in node.children) {
        final parts = child.path.split('/');
        if (parts.length >= 3 && parts[2] == projectId) {
          departmentNode = node;
          break;
        }
        
        // 이름에서 프로젝트 ID 추출 시도
        final nameMatch = RegExp(r'^([A-Z]\d+)').firstMatch(child.name);
        if (nameMatch != null && nameMatch.group(1) == projectId) {
          departmentNode = node;
          break;
        }
      }
      if (departmentNode != null) break;
    }
    
    if (departmentNode == null) {
      print('[WARNING] Department node not found for project: $projectId');
      return;
    }
    
    // 프로젝트 노드 찾기
    model.FileNode? projectNode;
    for (var child in departmentNode.children) {
      final parts = child.path.split('/');
      if (parts.length >= 3 && parts[2] == projectId) {
        projectNode = child;
        break;
      }
      
      // 이름에서 프로젝트 ID 추출 시도
      final nameMatch = RegExp(r'^([A-Z]\d+)').firstMatch(child.name);
      if (nameMatch != null && nameMatch.group(1) == projectId) {
        projectNode = child;
        break;
      }
    }
    
    if (projectNode == null) {
      print('[WARNING] Project node not found: $projectId');
      return;
    }
    
    // 프로젝트 노드 확장
    projectNode.isExpanded = true;
    await loadChildren(projectNode);
    
    // 모든 문서 노드 확장
    for (var docNode in projectNode.children) {
      docNode.isExpanded = true;
      await loadChildren(docNode);
    }
    
    print('[DEBUG] All documents expanded for project: $projectId');
    notifyListeners();
  }

  // 캐시 갱신 메서드
  Future<void> refreshCache() async {
    print('[DEBUG] Refreshing FileExplorerService cache');
    rootNodes = null;
    error = null;
    await apiService.refreshAllCache();
    await loadRootDirectory();
    print('[DEBUG] FileExplorerService cache refreshed');
    notifyListeners();
  }
  
  // 특정 프로젝트의 캐시만 갱신
  Future<void> refreshProjectCache(String projectId) async {
    print('[DEBUG] Refreshing cache for project: $projectId');
    await apiService.refreshProjectCache(projectId);
    
    // 프로젝트 노드 찾기 및 갱신
    if (rootNodes != null) {
      for (var departmentNode in rootNodes!) {
        for (var projectNode in departmentNode.children) {
          final parts = projectNode.path.split('/');
          if (parts.length >= 3 && parts[2] == projectId) {
            projectNode.children.clear();
            projectNode.isExpanded = false;
            break;
          }
          
          // 이름에서 프로젝트 ID 추출 시도
          final nameMatch = RegExp(r'^([A-Z]\d+)').firstMatch(projectNode.name);
          if (nameMatch != null && nameMatch.group(1) == projectId) {
            projectNode.children.clear();
            projectNode.isExpanded = false;
            break;
          }
        }
      }
    }
    
    print('[DEBUG] Cache refreshed for project: $projectId');
    notifyListeners();
  }
}