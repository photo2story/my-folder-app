import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/project_model.dart';
import 'file_explorer_service.dart';

class ApiService {
  static const String baseUrl = 'http://localhost:5000';
  static const String localBasePath = 'D:/github/my-folder-app';
  static const String resultsPath = 'static/results';

  Future<List<ProjectModel>> fetchProjects() async {
    try {
      print('[DEBUG] Fetching all projects from Flask server');
      final response = await http.get(
        Uri.parse('$baseUrl/audit_all'),
        headers: {'Accept': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final projectsData = data['projects'] as List<dynamic>;
        return projectsData
            .map((json) => ProjectModel.fromJson(json as Map<String, dynamic>))
            .toList();
      } else {
        print('[ERROR] Failed to load projects: ${response.statusCode}');
        print('[ERROR] Response body: ${response.body}');
        throw Exception('서버에서 프로젝트 목록을 가져오는데 실패했습니다');
      }
    } catch (e, stackTrace) {
      print('[ERROR] Error fetching projects: $e');
      print('[ERROR] Stack trace: $stackTrace');
      rethrow;
    }
  }

  Future<List<FileNode>> fetchDirectoryContents(String dirPath) async {
    try {
      print('[DEBUG] Fetching directory contents for path: $dirPath');
      // Return empty list for now
      return [];
    } catch (e, stackTrace) {
      print('[ERROR] Error fetching directory contents: $e');
      print('[ERROR] Stack trace: $stackTrace');
      return [];
    }
  }

  Future<ProjectModel> fetchProjectAudit(String projectId) async {
    try {
      print('[DEBUG] Fetching audit for project: $projectId');
      final response = await http.get(
        Uri.parse('$baseUrl/audit_project/$projectId?use_ai=true'),
        headers: {'Accept': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ProjectModel.fromJson(data);
      } else {
        print('[ERROR] Failed to load audit: ${response.statusCode}');
        print('[ERROR] Response body: ${response.body}');
        throw Exception('프로젝트 감사 데이터를 가져오는데 실패했습니다');
      }
    } catch (e, stackTrace) {
      print('[ERROR] Error loading audit data: $e');
      print('[ERROR] Stack trace: $stackTrace');
      rethrow;
    }
  }

  ProjectModel _getTestProjectData() {
    return ProjectModel(
      projectId: "20240178",
      projectName: "월곶~판교 복선전철 건설사업",
      department: "06010_환경사업부",
      status: "진행",
      contractor: "Unknown Contractor",
      documents: {
        "contract": {"exists": true, "details": []},
        "specification": {"exists": true, "details": []},
        "initiation": {"exists": true, "details": []},
        "agreement": {"exists": true, "details": []},
        "budget": {"exists": true, "details": []},
        "deliverable1": {"exists": true, "details": []},
        "deliverable2": {"exists": true, "details": []},
        "completion": {"exists": true, "details": []},
        "certificate": {"exists": true, "details": []},
        "evaluation": {"exists": true, "details": []}
      },
      timestamp: DateTime.now().toIso8601String(),
    );
  }

  void _logError(String method, dynamic error, [StackTrace? stackTrace]) {
    print('[ERROR] Error in $method: $error');
    if (stackTrace != null) {
      print('[ERROR] Stack trace: $stackTrace');
    }
  }
} 