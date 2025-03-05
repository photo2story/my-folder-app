// /my_flutter_app/lib/services/file_explorer_service.dart

import 'dart:io';
import 'package:path/path.dart' as path;
import 'api_service.dart';

class FileNode {
  final String path;
  final String label;
  final bool isDirectory;
  List<FileNode> children;
  DateTime? lastModified;

  FileNode({
    required this.path,
    required this.label,
    required this.isDirectory,
    this.children = const [],
    this.lastModified,
  });
}

class FileExplorerService {
  final ApiService _apiService = ApiService();
  
  // 캐시 저장소
  final Map<String, List<FileNode>> _cache = {};
  final Map<String, DateTime> _cacheTimestamps = {};
  static const Duration _cacheDuration = Duration(minutes: 5);

  Future<List<FileNode>> getDirectoryContents(String directoryPath) async {
    // 캐시 확인
    if (_cache.containsKey(directoryPath)) {
      final cacheTimestamp = _cacheTimestamps[directoryPath];
      if (cacheTimestamp != null && 
          DateTime.now().difference(cacheTimestamp) < _cacheDuration) {
        return _cache[directoryPath]!;
      }
    }

    try {
      // API를 통해 디렉토리 내용 가져오기
      final nodes = await _apiService.fetchDirectoryContents(directoryPath);

      // 캐시 업데이트
      _cache[directoryPath] = nodes;
      _cacheTimestamps[directoryPath] = DateTime.now();

      return nodes;
    } catch (e) {
      print('Error reading directory: $e');
      return [];
    }
  }

  Future<List<FileNode>> loadChildren(String parentPath) async {
    return await getDirectoryContents(parentPath);
  }

  void clearCache() {
    _cache.clear();
    _cacheTimestamps.clear();
  }

  // 초기 프로젝트 목록 가져오기
  Future<List<FileNode>> getAvailableProjects() async {
    try {
      return await _apiService.fetchProjects();
    } catch (e) {
      print('Error fetching projects: $e');
      return [];
    }
  }
}