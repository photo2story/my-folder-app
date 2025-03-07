import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:flutter/foundation.dart';
import '../models/project_model.dart';
import 'file_explorer_service.dart';

class ApiService {
  static const String localBasePath = 'D:/github/my-folder-app';
  static const String resultsPath = 'static/results';

  Future<List<ProjectModel>> fetchProjects() async {
    try {
      print('[DEBUG] Fetching projects from local JSON');
      if (kIsWeb) {
        return [_getTestProjectData()];  // 웹에서는 테스트 데이터 반환
      }

      final directory = Directory(path.join(localBasePath, resultsPath));
      final List<FileSystemEntity> files = directory.listSync();
      final List<ProjectModel> projects = [];

      for (var file in files) {
        if (file is File && file.path.endsWith('.json')) {
          try {
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

      return projects;
    } catch (e) {
      print('[ERROR] Error fetching projects: $e');
      return [_getTestProjectData()];  // 에러 발생 시 테스트 데이터 반환
    }
  }

  Future<ProjectModel> fetchProjectAudit(String projectId) async {
    try {
      print('[DEBUG] Fetching audit for project: $projectId');
      if (kIsWeb) {
        return _getTestProjectData();  // 웹에서는 테스트 데이터 반환
      }

      final file = File(path.join(localBasePath, resultsPath, 'audit_$projectId.json'));
      final jsonString = await file.readAsString();
      final List<dynamic> jsonData = json.decode(jsonString);
      
      if (jsonData.isEmpty) {
        throw Exception('No data found for project $projectId');
      }
      
      return ProjectModel.fromJson(jsonData[0]);
    } catch (e) {
      print('[ERROR] Error loading audit data: $e');
      return _getTestProjectData();  // 에러 발생 시 테스트 데이터 반환
    }
  }

  Future<ProjectModel> fetchLocalProjectData(String projectId) async {
    return fetchProjectAudit(projectId);  // fetchProjectAudit를 재사용
  }

  Future<List<FileNode>> fetchDirectoryContents(String dirPath) async {
    try {
      print('[DEBUG] Fetching directory contents for path: $dirPath');
      if (kIsWeb) {
        return [];
      }

      final parts = dirPath.split('/');
      
      // 최상위 레벨: 부서 목록
      if (parts.length == 1) {
        final projects = await fetchProjects();
        final departments = <String>{};
        for (var project in projects) {
          departments.add(project.department);
        }
        
        return departments.map((dept) => FileNode(
          name: dept,
          path: "$dirPath/$dept",
          isDirectory: true,
          children: [],
        )).toList();
      }

      // 부서 레벨: 해당 부서의 프로젝트 목록
      if (parts.length == 2) {
        final department = parts[1];
        final projects = await fetchProjects();
        final deptProjects = projects.where((p) => p.department == department);
        
        return deptProjects.map((project) => FileNode(
          name: "${project.projectId} (${project.projectName} - ${project.status} - ${project.contractor})",
          path: "$dirPath/${project.projectId}",
          isDirectory: true,
          children: [],
        )).toList();
      }

      // 프로젝트 레벨: 문서 타입 폴더들
      if (parts.length == 3) {
        final projectId = parts[2];
        final projectData = await fetchProjectAudit(projectId);
        
        return [
          FileNode(
            name: "계약서",
            path: "$dirPath/contract",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "과업지시서",
            path: "$dirPath/specification",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "착수계",
            path: "$dirPath/initiation",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "업무협정",
            path: "$dirPath/agreement",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "실행예산",
            path: "$dirPath/budget",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "보고서",
            path: "$dirPath/deliverable1",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "도면",
            path: "$dirPath/deliverable2",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "준공계",
            path: "$dirPath/completion",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "실적증명",
            path: "$dirPath/certificate",
            isDirectory: true,
            children: [],
          ),
          FileNode(
            name: "평가",
            path: "$dirPath/evaluation",
            isDirectory: true,
            children: [],
          ),
        ];
      }

      // 문서 타입 레벨: 실제 파일들
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
            
            return FileNode(
              name: fileName,
              path: filePath,
              isDirectory: false,
              children: [],
            );
          } catch (e) {
            print('[ERROR] Error parsing file info: $e');
            return FileNode(
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