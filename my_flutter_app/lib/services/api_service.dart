// /my_flutter_app/lib/services/api_service.dart

import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:flutter/foundation.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;
import 'package:my_flutter_app/models/project_model.dart';
import 'file_explorer_service.dart';

class ApiService {
  static const String localBasePath = 'D:/github/my-folder-app';
  static const String resultsPath = 'static/results';

  Future<List<ProjectModel>> fetchProjects() async {
    try {
      print('[DEBUG] Fetching projects from local JSON at $localBasePath/$resultsPath');
      if (kIsWeb) {
        print('[DEBUG] Web platform detected, returning test data');
        return [_getTestProjectData()];
      }

      final directory = Directory(path.join(localBasePath, resultsPath));
      if (!await directory.exists()) {
        print('[ERROR] Directory does not exist: ${directory.path}');
        return [_getTestProjectData()];
      }
      final List<FileSystemEntity> files = directory.listSync();
      final List<ProjectModel> projects = [];

      for (var file in files) {
        if (file is File && file.path.endsWith('.json')) {
          try {
            print('[DEBUG] Processing file: ${file.path}');
            final jsonString = await file.readAsString();
            final List<dynamic> jsonData = json.decode(jsonString);
            if (jsonData.isNotEmpty) {
              projects.add(ProjectModel.fromJson(jsonData[0]));
            }
          } catch (e) {
            print('[ERROR] Error reading file ${file.path}: $e');
            continue;
          }
        }
      }

      if (projects.isEmpty) {
        print('[WARNING] No project data found, returning test data');
        return [_getTestProjectData()];
      }

      print('[DEBUG] Fetched ${projects.length} projects');
      return projects;
    } catch (e) {
      print('[ERROR] Error fetching projects: $e');
      return [_getTestProjectData()];
    }
  }

  Future<ProjectModel> fetchProjectAudit(String projectId) async {
    try {
      print('[DEBUG] Fetching audit for project: $projectId');
      if (kIsWeb) {
        print('[DEBUG] Web platform, returning test data');
        return _getTestProjectData();
      }

      final file = File(path.join(localBasePath, resultsPath, 'audit_$projectId.json'));
      if (!await file.exists()) {
        print('[ERROR] File not found: ${file.path}');
        return _getTestProjectData();
      }
      final jsonString = await file.readAsString();
      final List<dynamic> jsonData = json.decode(jsonString);
      
      if (jsonData.isEmpty) {
        throw Exception('No data found for project $projectId');
      }
      
      return ProjectModel.fromJson(jsonData[0]);
    } catch (e) {
      print('[ERROR] Error loading audit data: $e');
      return _getTestProjectData();
    }
  }

  Future<ProjectModel> fetchLocalProjectData(String projectId) async {
    return fetchProjectAudit(projectId);
  }

  Future<List<model.FileNode>> fetchDirectoryContents(String dirPath) async {
    try {
      print('[DEBUG] Fetching directory contents for path: $dirPath');
      if (kIsWeb) {
        // 웹 환경에서 테스트 데이터 제공
        final parts = dirPath.split('/');
        if (parts.length == 1) {
          return [
            model.FileNode(
              name: "06010_환경사업부",
              path: "$dirPath/06010_환경사업부",
              isDirectory: true,
              children: [],
            ),
          ];
        }
        if (parts.length == 2 && parts[1] == "06010_환경사업부") {
          return [
            model.FileNode(
              name: "20240178 (월곶~판교 복선전철 건설사업 - 진행 - Unknown Contractor)",
              path: "$dirPath/20240178",
              isDirectory: true,
              children: [],
            ),
          ];
        }
        if (parts.length == 3 && parts[2] == "20240178") {
          return [
            model.FileNode(name: "계약서", path: "$dirPath/contract", isDirectory: true, children: []),
            model.FileNode(name: "과업지시서", path: "$dirPath/specification", isDirectory: true, children: []),
            model.FileNode(name: "착수계", path: "$dirPath/initiation", isDirectory: true, children: []),
            model.FileNode(name: "업무협정", path: "$dirPath/agreement", isDirectory: true, children: []),
            model.FileNode(name: "실행예산", path: "$dirPath/budget", isDirectory: true, children: []),
            model.FileNode(name: "보고서", path: "$dirPath/deliverable1", isDirectory: true, children: []),
            model.FileNode(name: "도면", path: "$dirPath/deliverable2", isDirectory: true, children: []),
            model.FileNode(name: "준공계", path: "$dirPath/completion", isDirectory: true, children: []),
            model.FileNode(name: "실적증명", path: "$dirPath/certificate", isDirectory: true, children: []),
            model.FileNode(name: "평가", path: "$dirPath/evaluation", isDirectory: true, children: []),
          ];
        }
        if (parts.length == 4) {
          return [
            model.FileNode(name: "sample.pdf", path: "https://example.com/sample.pdf", isDirectory: false, children: []),
          ];
        }
        return [];
      }

      final parts = dirPath.split('/');

      if (parts.length == 1) {
        final projects = await fetchProjects();
        final departments = <String>{};
        for (var project in projects) {
          departments.add(project.department);
        }
        
        return departments.map((dept) => model.FileNode(
          name: dept,
          path: "$dirPath/$dept",
          isDirectory: true,
          children: [],
        )).toList();
      }

      if (parts.length == 2) {
        final department = parts[1];
        final projects = await fetchProjects();
        final deptProjects = projects.where((p) => p.department == department);
        
        return deptProjects.map((project) => model.FileNode(
          name: "${project.projectId} (${project.projectName} - ${project.status} - ${project.contractor})",
          path: "$dirPath/${project.projectId}",
          isDirectory: true,
          children: [],
        )).toList();
      }

      if (parts.length == 3) {
        final projectId = parts[2];
        final projectData = await fetchProjectAudit(projectId);
        
        return [
          model.FileNode(name: "계약서", path: "$dirPath/contract", isDirectory: true, children: []),
          model.FileNode(name: "과업지시서", path: "$dirPath/specification", isDirectory: true, children: []),
          model.FileNode(name: "착수계", path: "$dirPath/initiation", isDirectory: true, children: []),
          model.FileNode(name: "업무협정", path: "$dirPath/agreement", isDirectory: true, children: []),
          model.FileNode(name: "실행예산", path: "$dirPath/budget", isDirectory: true, children: []),
          model.FileNode(name: "보고서", path: "$dirPath/deliverable1", isDirectory: true, children: []),
          model.FileNode(name: "도면", path: "$dirPath/deliverable2", isDirectory: true, children: []),
          model.FileNode(name: "준공계", path: "$dirPath/completion", isDirectory: true, children: []),
          model.FileNode(name: "실적증명", path: "$dirPath/certificate", isDirectory: true, children: []),
          model.FileNode(name: "평가", path: "$dirPath/evaluation", isDirectory: true, children: []),
        ];
      }

      if (parts.length == 4) {
        final projectId = parts[2];
        final docType = parts[3];
        final projectData = await fetchProjectAudit(projectId);
        final docDetails = projectData.documents[docType]?['details'] as List<dynamic>? ?? [];
        
        return docDetails.map((detail) {
          try {
            final Map<String, dynamic> fileInfo = json.decode(detail['name'].toString().replaceAll("'", '"'));
            final String fileName = fileInfo['name'] as String;
            final String filePath = fileInfo['full_path'] as String;
            
            return model.FileNode(
              name: fileName,
              path: filePath,
              isDirectory: false,
              children: [],
            );
          } catch (e) {
            print('[ERROR] Error parsing file info: $e');
            return model.FileNode(
              name: detail['name']?.toString() ?? '알 수 없는 파일',
              path: detail['path']?.toString() ?? '',
              isDirectory: false,
              children: [],
            );
          }
        }).toList();
      }

      return [];
    } catch (e) {
      print('[ERROR] Error fetching directory contents: $e');
      return [];
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