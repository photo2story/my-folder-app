// /my_flutter_app/lib/services/api_service.dart

import 'dart:convert';
import 'dart:io';
import 'package:csv/csv.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:my_flutter_app/models/file_node.dart' as model;
import 'package:my_flutter_app/models/project_model.dart';
import 'file_explorer_service.dart';

class ApiService {
  static const String basePath = 'D:/github/MY-FOLDER-APP';
  static const String csvPath = 'static/report/combined_report.csv';
  static const String resultsPath = 'static/results';
  static const String githubBaseUrl = 'https://raw.githubusercontent.com/photo2story/my-folder-app/main';

  Future<List<ProjectModel>> fetchProjects() async {
    print("\n=== FETCH PROJECTS DEBUG ===");
    print("[DEBUG] Starting fetchProjects in ApiService");
    try {
      print("[DEBUG] Fetching CSV from: $githubBaseUrl/$csvPath");
      if (kIsWeb) {
        final response = await http.get(Uri.parse('$githubBaseUrl/$csvPath'));
        print("[DEBUG] CSV Response status: ${response.statusCode}");

        if (response.statusCode != 200) {
          print("[ERROR] Failed to load CSV: ${response.statusCode} - ${response.body}");
          return [_getTestProjectData()];
        }

        final csvString = response.body;
        List<String> lines = LineSplitter.split(csvString).toList();
        print("[DEBUG] Received ${lines.length} lines of CSV data");
        if (lines.isNotEmpty) {
          print("[DEBUG] CSV Headers: ${lines[0]}");
          print("[DEBUG] First data row: ${lines.length > 1 ? lines[1] : 'No data'}");
        }

        final csvSettings = CsvToListConverter(
          fieldDelimiter: ',',
          eol: '\n',
          textDelimiter: '"',
          shouldParseNumbers: false,
        );
        final List<List<dynamic>> csvData = csvSettings.convert(csvString);
        print("[DEBUG] Converted CSV data length: ${csvData.length}");

        final List<ProjectModel> projects = [];
        for (var row in csvData.skip(1)) {
          print("[DEBUG] Processing row: $row");
          if (row.length >= 7) {
            final departProjectId = row[6].toString();
            final department = row[2].toString();
            final codePrefix = departProjectId.length >= 5 ? departProjectId.substring(0, 5) : '00000';
            final subFolder = '${codePrefix}_${department}'.replaceAll('\\', '/');
            final documents = {
              "contract": {"exists": int.parse(row[8].toString()), "details": [], "subFolder": subFolder},
              "specification": {"exists": int.parse(row[9].toString()), "details": [], "subFolder": subFolder},
              "initiation": {"exists": int.parse(row[10].toString()), "details": [], "subFolder": subFolder},
              "agreement": {"exists": int.parse(row[11].toString()), "details": [], "subFolder": subFolder},
              "budget": {"exists": int.parse(row[12].toString()), "details": [], "subFolder": subFolder},
              "deliverable1": {"exists": int.parse(row[13].toString()), "details": [], "subFolder": subFolder},
              "deliverable2": {"exists": int.parse(row[14].toString()), "details": [], "subFolder": subFolder},
              "completion": {"exists": int.parse(row[15].toString()), "details": [], "subFolder": subFolder},
              "certificate": {"exists": int.parse(row[16].toString()), "details": [], "subFolder": subFolder},
              "evaluation": {"exists": int.parse(row[17].toString()), "details": [], "subFolder": subFolder},
            };
            projects.add(ProjectModel(
              projectId: row[0].toString(),
              projectName: row[1].toString(),
              department: row[2].toString(),
              status: row[3].toString(),
              contractor: row[4].toString(),
              documents: documents,
              timestamp: DateTime.now().toIso8601String(),
            ));
          } else {
            print("[WARNING] Row $row has insufficient columns: ${row.length}");
          }
        }

        if (projects.isEmpty) {
          print("[WARNING] No project data found in GitHub CSV");
          return [_getTestProjectData()];
        }

        print("[DEBUG] Fetched ${projects.length} projects from GitHub");
        return projects;
      }

      final filePath = '$basePath/$csvPath';
      final file = File(filePath);
      if (!await file.exists()) {
        print('[ERROR] CSV file not found: $filePath');
        return [_getTestProjectData()];
      }

      final csvString = await file.readAsString();
      final List<List<dynamic>> csvData = const CsvToListConverter().convert(csvString);
      final List<ProjectModel> projects = [];
      for (var row in csvData.skip(1)) {
        if (row.length >= 5) {
          projects.add(ProjectModel(
            projectId: row[0].toString(),
            projectName: row[1].toString(),
            department: row[2].toString(),
            status: row[3].toString(),
            contractor: row[4].toString(),
            documents: {},
            timestamp: DateTime.now().toIso8601String(),
          ));
        }
      }

      if (projects.isEmpty) {
        print('[WARNING] No project data found in CSV');
        return [_getTestProjectData()];
      }

      print("[DEBUG] Fetched ${projects.length} projects from local CSV");
      return projects;
    } catch (e, stackTrace) {
      print("[ERROR] Error in fetchProjects:");
      print(e);
      print("Stack trace:");
      print(stackTrace);
      return [_getTestProjectData()];
    }
  }

  Future<ProjectModel> fetchProjectAudit(String projectId) async {
    print("\n=== FETCH PROJECT AUDIT DEBUG ===");
    print("[DEBUG] Fetching audit for project: $projectId");
    try {
      final projects = await fetchProjects();
      final project = projects.firstWhere((p) => p.projectId == projectId, orElse: () => _getTestProjectData());
      final subFolder = project.documents["contract"]?["subFolder"] ?? '';

      final jsonPath = subFolder.isNotEmpty
          ? '$githubBaseUrl/$resultsPath/$subFolder/audit_$projectId.json'
          : '$githubBaseUrl/$resultsPath/audit_$projectId.json';
      print("[DEBUG] Attempting to fetch JSON from: $jsonPath");

      if (kIsWeb) {
        final response = await http.get(Uri.parse(jsonPath));
        print("[DEBUG] JSON Response status: ${response.statusCode}");
        if (response.statusCode != 200) {
          print('[ERROR] Failed to fetch JSON from GitHub: ${response.statusCode} - ${response.body}');
          return _getTestProjectData();
        }

        final jsonString = response.body;
        final dynamic jsonData = json.decode(jsonString);
        print("[DEBUG] JSON data: $jsonData");

        if (jsonData is List<dynamic> && jsonData.isNotEmpty) {
          print("[DEBUG] JSON data is a list, using first element");
          return ProjectModel.fromJson(jsonData[0]);
        } else if (jsonData is Map<String, dynamic>) {
          print("[DEBUG] JSON data is a map, using directly");
          // 웹 환경: full_path를 GitHub URL로 변환
          final updatedData = jsonData;
          if (updatedData['documents'] != null) {
            for (var docType in updatedData['documents'].keys) {
              final docDetails = updatedData['documents'][docType]['details'] as List<dynamic>? ?? [];
              for (var detail in docDetails) {
                final fileName = detail['name']?.toString() ?? '';
                if (fileName.isNotEmpty) {
                  final githubFilePath = Uri.encodeFull('$githubBaseUrl/$resultsPath/$subFolder/$fileName');
                  detail['full_path'] = githubFilePath;
                  print("[DEBUG] Updated full_path for $fileName: $githubFilePath");
                }
              }
            }
          }
          return ProjectModel.fromJson(updatedData);
        } else {
          throw Exception('Invalid JSON format for project $projectId');
        }
      } else {
        // 로컬 환경: 네트워크 드라이브 경로 사용
        final filePath = '$basePath/$resultsPath/audit_$projectId.json';
        final file = File(filePath);
        if (!await file.exists()) {
          print('[ERROR] JSON file not found: $filePath');
          return _getTestProjectData();
        }

        final jsonString = await file.readAsString();
        final dynamic jsonData = json.decode(jsonString);

        if (jsonData is List<dynamic> && jsonData.isNotEmpty) {
          return ProjectModel.fromJson(jsonData[0]);
        } else if (jsonData is Map<String, dynamic>) {
          print("[DEBUG] Using network drive path for full_path in local environment");
          return ProjectModel.fromJson(jsonData);
        } else {
          throw Exception('Invalid JSON format for project $projectId');
        }
      }
    } catch (e, stackTrace) {
      print("[ERROR] Error in fetchProjectAudit:");
      print(e);
      print("Stack trace:");
      print(stackTrace);
      return _getTestProjectData();
    }
  }

  Future<ProjectModel> fetchLocalProjectData(String projectId) async {
    return fetchProjectAudit(projectId);
  }

Future<List<model.FileNode>> fetchDirectoryContents(String dirPath) async {
  print("\n=== FETCH DIRECTORY CONTENTS DEBUG ===");
  print('[DEBUG] Fetching directory contents for path: $dirPath');
  try {
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
      final projectBasePath = projectData.projectPath ?? ''; // 네트워크 드라이브 경로

      if (docDetails.isEmpty && projectData.documents.containsKey(docType)) {
        final exists = projectData.documents[docType]!['exists'] as int;
        if (exists > 0) {
          final fileName = "${docType.toLowerCase()}_${projectId}.pdf";
          final fullPath = '$projectBasePath\\01. 행정\\01. 계약\\02.계약서\\2차(2025년)\\$fileName'; // 경로 조정
          docDetails.add({
            "name": fileName,
            "full_path": fullPath,
          });
        }
      }

      return docDetails.map((detail) {
        try {
          final fileName = detail['name']?.toString() ?? '';
          final filePath = detail['full_path']?.toString() ?? '';
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
            path: detail['full_path']?.toString() ?? '',
            isDirectory: false,
            children: [],
          );
        }
      }).toList();
    }

    return [];
  } catch (e, stackTrace) {
    print("[ERROR] Error in fetchDirectoryContents:");
    print(e);
    print("Stack trace:");
    print(stackTrace);
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
        "contract": {
          "exists": true,
          "details": [
            {
              "name": "contract_20240178.pdf",
              "full_path": "Z:\\06010_환경\\2팀\\02.사후환경영향조사\\20240178ㅣ월곶_판교 복선전철 건설사업(제2_5, 7, 9_10공구) 사후환경영향조사용역\\01. 행정\\01. 계약\\contract_20240178.pdf"
            }
          ]
        },
        "specification": {
          "exists": true,
          "details": [
            {
              "name": "spec_20240178.pdf",
              "full_path": "Z:\\06010_환경\\2팀\\02.사후환경영향조사\\20240178ㅣ월곶_판교 복선전철 건설사업(제2_5, 7, 9_10공구) 사후환경영향조사용역\\01. 행정\\01. 계약\\spec_20240178.pdf"
            }
          ]
        },
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
    print('[ERROR] $method: $error');
    if (stackTrace != null) {
      print('[ERROR] Stack trace: $stackTrace');
    }
  }
}