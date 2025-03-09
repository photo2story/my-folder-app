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

  // 부서 매핑 추가 (config_assets.py에서 가져온 매핑)
  static final Map<String, String> DEPARTMENT_MAPPING = {
    '도로부': '01010',
    '공항및인프라사업부': '01020',
    '구조부': '01030',
    '지반부': '01040',
    '교통부': '01050',
    '안전진단부': '01060',
    '도시철도부': '02010',
    '철도설계부': '03010',
    '철도건설관리부': '03020',
    '도시계획부': '04010',
    '도시설계부': '04020',
    '조경부': '04030',
    '수자원부': '05010',
    '환경사업부': '06010',
    '상하수도부': '07010',
    '항만부': '07020',
    '건설사업관리부': '08010',
    '해외영업부': '09010',
    '플랫폼사업실': '10010',
    '기술지원실': '11010',
    '수성엔지니어링': '99999'
  };

  // 부서 코드 → 부서명 매핑 (역방향 매핑)
  static final Map<String, String> DEPARTMENT_NAMES = {
    '01010': '도로부',
    '01020': '공항및인프라사업부',
    '01030': '구조부',
    '01040': '지반부',
    '01050': '교통부',
    '01060': '안전진단부',
    '02010': '도시철도부',
    '03010': '철도설계부',
    '03020': '철도건설관리부',
    '04010': '도시계획부',
    '04020': '도시설계부',
    '04030': '조경부',
    '05010': '수자원부',
    '06010': '환경사업부',
    '07010': '상하수도부',
    '07020': '항만부',
    '08010': '건설사업관리부',
    '09010': '해외영업부',
    '10010': '플랫폼사업실',
    '11010': '기술지원실',
    '99999': '수성엔지니어링'
  };

  // 캐시 맵 추가
  final Map<String, List<model.FileNode>> _directoryCache = {};
  final Map<String, ProjectModel> _projectCache = {};
  final Map<String, List<ProjectModel>> _projectsListCache = {};
  
  // 캐시 초기화 메서드
  void clearCache() {
    _directoryCache.clear();
    _projectCache.clear();
    _projectsListCache.clear();
    print("[DEBUG] Cache cleared");
  }
  
  // 특정 프로젝트의 캐시만 갱신
  Future<void> refreshProjectCache(String projectId) async {
    print("[DEBUG] Refreshing cache for project: $projectId");
    _projectCache.remove(projectId);
    
    // 프로젝트 관련 디렉토리 캐시도 삭제
    _directoryCache.removeWhere((key, value) => key.contains(projectId));
    
    // 프로젝트 데이터 다시 가져오기
    await fetchProjectAudit(projectId);
    print("[DEBUG] Cache refreshed for project: $projectId");
  }
  
  // 전체 캐시 갱신
  Future<void> refreshAllCache() async {
    print("[DEBUG] Refreshing all cache");
    clearCache();
    
    // 프로젝트 목록 다시 가져오기
    await fetchProjects();
    print("[DEBUG] All cache refreshed");
  }

  // 부서명에서 부서 코드 가져오기
  String getDepartmentCode(String departmentName) {
    return DEPARTMENT_MAPPING[departmentName] ?? '99999';
  }

  // 부서 코드에서 부서명 가져오기
  String getDepartmentName(String departmentCode) {
    return DEPARTMENT_NAMES[departmentCode] ?? '미정의 부서';
  }

  Future<List<ProjectModel>> fetchProjects() async {
    print("\n=== FETCH PROJECTS DEBUG ===");
    print("[DEBUG] Starting fetchProjects in ApiService");
    
    // 캐시에 있는 경우 캐시된 데이터 반환
    if (_projectsListCache.containsKey('all')) {
      print("[DEBUG] Returning cached projects list (${_projectsListCache['all']!.length} items)");
      return _projectsListCache['all']!;
    }
    
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
            // 부서 정보 추출
            final departProjectId = row[6].toString(); // Depart_ProjectID (예: 10010_A20230001)
            final departmentName = row[2].toString(); // Depart (예: 플랫폼사업실)
            
            // 부서 코드 추출 (Depart_ProjectID에서 첫 부분)
            String departmentCode = '';
            if (departProjectId.contains('_')) {
              departmentCode = departProjectId.split('_')[0];
              print("[DEBUG] Extracted department code from Depart_ProjectID: $departmentCode");
            } else {
              // 부서 코드가 없는 경우 매핑에서 찾기
              departmentCode = getDepartmentCode(departmentName);
              print("[DEBUG] Mapped department code from name: $departmentCode");
            }
            
            // 부서 정보 저장 형식: "코드_이름" (예: 10010_플랫폼사업실)
            final department = "${departmentCode}_$departmentName";
            print("[DEBUG] Formatted department: $department");
            
            // 문서 정보 구성
            final documents = {
              "contract": {"exists": int.parse(row[8].toString()), "details": []},
              "specification": {"exists": int.parse(row[9].toString()), "details": []},
              "initiation": {"exists": int.parse(row[10].toString()), "details": []},
              "agreement": {"exists": int.parse(row[11].toString()), "details": []},
              "budget": {"exists": int.parse(row[12].toString()), "details": []},
              "deliverable1": {"exists": int.parse(row[13].toString()), "details": []},
              "deliverable2": {"exists": int.parse(row[14].toString()), "details": []},
              "completion": {"exists": int.parse(row[15].toString()), "details": []},
              "certificate": {"exists": int.parse(row[16].toString()), "details": []},
              "evaluation": {"exists": int.parse(row[17].toString()), "details": []}
            };
            
            projects.add(ProjectModel(
              projectId: row[0].toString(),
              projectName: row[1].toString(),
              department: department,
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
        _projectsListCache['all'] = projects;
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
        if (row.length >= 7) {
          // 부서 정보 추출
          final departProjectId = row[6].toString(); // Depart_ProjectID (예: 10010_A20230001)
          final departmentName = row[2].toString(); // Depart (예: 플랫폼사업실)
          
          // 부서 코드 추출 (Depart_ProjectID에서 첫 부분)
          String departmentCode = '';
          if (departProjectId.contains('_')) {
            departmentCode = departProjectId.split('_')[0];
            print("[DEBUG] Extracted department code from Depart_ProjectID: $departmentCode");
          } else {
            // 부서 코드가 없는 경우 매핑에서 찾기
            departmentCode = getDepartmentCode(departmentName);
            print("[DEBUG] Mapped department code from name: $departmentCode");
          }
          
          // 부서 정보 저장 형식: "코드_이름" (예: 10010_플랫폼사업실)
          final department = "${departmentCode}_$departmentName";
          print("[DEBUG] Formatted department: $department");
          
          // 문서 정보 구성
          final documents = {
            "contract": {"exists": int.parse(row[8].toString()), "details": []},
            "specification": {"exists": int.parse(row[9].toString()), "details": []},
            "initiation": {"exists": int.parse(row[10].toString()), "details": []},
            "agreement": {"exists": int.parse(row[11].toString()), "details": []},
            "budget": {"exists": int.parse(row[12].toString()), "details": []},
            "deliverable1": {"exists": int.parse(row[13].toString()), "details": []},
            "deliverable2": {"exists": int.parse(row[14].toString()), "details": []},
            "completion": {"exists": int.parse(row[15].toString()), "details": []},
            "certificate": {"exists": int.parse(row[16].toString()), "details": []},
            "evaluation": {"exists": int.parse(row[17].toString()), "details": []}
          };
          
          projects.add(ProjectModel(
            projectId: row[0].toString(),
            projectName: row[1].toString(),
            department: department,
            status: row[3].toString(),
            contractor: row[4].toString(),
            documents: documents,
            timestamp: DateTime.now().toIso8601String(),
          ));
        }
      }

      if (projects.isEmpty) {
        print('[WARNING] No project data found in CSV');
        return [_getTestProjectData()];
      }

      print("[DEBUG] Fetched ${projects.length} projects from local CSV");
      _projectsListCache['all'] = projects;
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
    
    // 캐시에 있는 경우 캐시된 데이터 반환
    if (_projectCache.containsKey(projectId)) {
      print("[DEBUG] Returning cached project data for: $projectId");
      return _projectCache[projectId]!;
    }
    
    try {
      // 프로젝트 ID에서 접두사 처리 (C20240178 -> 20240178)
      final numericProjectId = projectId.replaceAll(RegExp(r'[A-Za-z]'), '');
      print("[DEBUG] Numeric project ID: $numericProjectId");
      
      // 프로젝트 기본 정보 가져오기
      final projects = await fetchProjects();
      final project = projects.firstWhere(
        (p) => p.projectId == projectId || p.projectId == numericProjectId, 
        orElse: () => _getTestProjectData()
      );
      
      // 부서 정보 추출 - config_assets.py 매핑 사용
      String departmentCode = '';
      String departmentName = '';
      
      if (project.department.contains('_')) {
        // 이미 "코드_이름" 형식인 경우
        final parts = project.department.split('_');
        departmentCode = parts[0];
        departmentName = parts.length > 1 ? parts[1] : getDepartmentName(departmentCode);
      } else {
        // 부서명만 있는 경우
        departmentName = project.department;
        departmentCode = getDepartmentCode(departmentName);
        
        // 부서명이 매핑에 없는 경우, 부서명이 코드일 수도 있음
        if (departmentCode == '99999' && DEPARTMENT_NAMES.containsKey(departmentName)) {
          departmentCode = departmentName;
          departmentName = getDepartmentName(departmentCode);
        }
      }
      
      print("[DEBUG] Department code: $departmentCode");
      print("[DEBUG] Department name: $departmentName");
      
      // JSON 파일 경로 구성 - 부서코드_부서명 형식으로 변경
      final folderPath = "${departmentCode}_$departmentName";
      final jsonPath = kIsWeb
          ? '$githubBaseUrl/$resultsPath/$folderPath/audit_$projectId.json'
          : '$basePath/$resultsPath/$folderPath/audit_$projectId.json';
      
      print("[DEBUG] Attempting to fetch JSON from: $jsonPath");
      
      // 웹 환경에서의 처리
      if (kIsWeb) {
        final response = await http.get(Uri.parse(jsonPath));
        print("[DEBUG] JSON Response status: ${response.statusCode}");
        
        // 첫 번째 경로로 실패하면 다른 형식의 경로 시도
        if (response.statusCode != 200) {
          print("[DEBUG] First path failed, trying alternative paths");
          
          // 여러 대체 경로 시도
          final alternativePaths = [
            '$githubBaseUrl/$resultsPath/audit_$projectId.json',
            '$githubBaseUrl/$resultsPath/$departmentCode/audit_$projectId.json',
            '$githubBaseUrl/$resultsPath/$departmentName/audit_$projectId.json',
            '$githubBaseUrl/$resultsPath/${departmentCode}_${departmentName.replaceAll(' ', '')}/audit_$projectId.json'
          ];
          
          for (final altPath in alternativePaths) {
            print("[DEBUG] Trying alternative path: $altPath");
            final altResponse = await http.get(Uri.parse(altPath));
            if (altResponse.statusCode == 200) {
              print("[DEBUG] Found JSON at: $altPath");
              final jsonString = altResponse.body;
              final dynamic jsonData = json.decode(jsonString);
              
              if (jsonData is List<dynamic> && jsonData.isNotEmpty) {
                final projectModel = ProjectModel.fromJson(jsonData[0]);
                _projectCache[projectId] = projectModel;
                return projectModel;
              } else if (jsonData is Map<String, dynamic>) {
                final projectModel = ProjectModel.fromJson(jsonData);
                _projectCache[projectId] = projectModel;
                return projectModel;
              }
            }
          }
          
          print('[ERROR] Failed to fetch JSON from GitHub in any path');
          return _getTestProjectData();
        }
        
        // 원래 경로에서 성공한 경우
        final jsonString = response.body;
        final dynamic jsonData = json.decode(jsonString);
        print("[DEBUG] JSON data: $jsonData");
        
        if (jsonData is List<dynamic> && jsonData.isNotEmpty) {
          final projectModel = ProjectModel.fromJson(jsonData[0]);
          _projectCache[projectId] = projectModel;
          return projectModel;
        } else if (jsonData is Map<String, dynamic>) {
          final projectModel = ProjectModel.fromJson(jsonData);
          _projectCache[projectId] = projectModel;
          return projectModel;
        }
      } else {
        // 로컬 환경에서의 처리
        // 여러 가능한 경로 시도
        final possiblePaths = [
          '$basePath/$resultsPath/$folderPath/audit_$projectId.json',
          '$basePath/$resultsPath/audit_$projectId.json',
          '$basePath/$resultsPath/$departmentCode/audit_$projectId.json',
          '$basePath/$resultsPath/$departmentName/audit_$projectId.json',
          '$basePath/$resultsPath/${departmentCode}_${departmentName.replaceAll(' ', '')}/audit_$projectId.json'
        ];
        
        for (final path in possiblePaths) {
          print("[DEBUG] Trying path: $path");
          final file = File(path);
          if (await file.exists()) {
            print("[DEBUG] Found file at: $path");
            final jsonString = await file.readAsString();
            final dynamic jsonData = json.decode(jsonString);
            
            if (jsonData is List<dynamic> && jsonData.isNotEmpty) {
              final projectModel = ProjectModel.fromJson(jsonData[0]);
              _projectCache[projectId] = projectModel;
              return projectModel;
            } else if (jsonData is Map<String, dynamic>) {
              final projectModel = ProjectModel.fromJson(jsonData);
              _projectCache[projectId] = projectModel;
              return projectModel;
            }
          }
        }
        
        print('[ERROR] JSON file not found in any of the possible paths');
      }
      
      // 모든 시도 실패 시 테스트 데이터 반환
      return _getTestProjectData();
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
    
    // 캐시에 있는 경우 캐시된 데이터 반환
    if (_directoryCache.containsKey(dirPath)) {
      print("[DEBUG] Returning cached directory contents for: $dirPath (${_directoryCache[dirPath]!.length} items)");
      return _directoryCache[dirPath]!;
    }
    
    try {
      final parts = dirPath.split('/');

      if (parts.length == 1) {
        final projects = await fetchProjects();
        // Set을 사용하여 중복 제거
        final departments = <String>{};
        for (var project in projects) {
          if (project.department.isNotEmpty) {
            departments.add(project.department);
          }
        }

        final result = departments.toList()
          ..sort();  // 정렬 추가
        
        final nodes = result.map((dept) => model.FileNode(
          name: dept,
          path: "$dirPath/$dept",
          isDirectory: true,
          children: [],
        )).toList();
        
        // 결과를 캐시에 저장
        _directoryCache[dirPath] = nodes;
        return nodes;
      }

      if (parts.length == 2) {
        final department = parts[1];
        final projects = await fetchProjects();
        // Set을 사용하여 중복 제거
        final projectMap = <String, ProjectModel>{};
        
        for (var project in projects.where((p) => p.department == department)) {
          projectMap[project.projectId] = project;
        }
        
        final result = projectMap.values.map((project) => model.FileNode(
          name: "${project.projectId} (${project.projectName} - ${project.status} - ${project.contractor})",
          path: "$dirPath/${project.projectId}",
          isDirectory: true,
          children: [],
        )).toList()
          ..sort((a, b) => a.name.compareTo(b.name));  // 정렬 추가
        
        // 결과를 캐시에 저장
        _directoryCache[dirPath] = result;
        return result;
      }

      if (parts.length == 3) {
        final projectId = parts[2];
        final projectData = await fetchProjectAudit(projectId);
        
        // 문서 타입 순서 정의
        final orderedDocTypes = [
          'contract',
          'specification',
          'initiation',
          'agreement',
          'budget',
          'deliverable1',
          'deliverable2',
          'completion',
          'certificate',
          'evaluation'
        ];
        
        final result = orderedDocTypes.map((type) => model.FileNode(
          name: _getDocumentTypeName(type),
          path: "$dirPath/$type",
          isDirectory: true,
          children: [],
        )).toList();
        
        // 결과를 캐시에 저장
        _directoryCache[dirPath] = result;
        return result;
      }

      if (parts.length == 4) {
        final projectId = parts[2];
        final docType = parts[3];
        final projectData = await fetchProjectAudit(projectId);
        
        // 중복 파일 제거를 위해 Map 사용 (파일명을 키로 사용)
        final uniqueFiles = <String, model.FileNode>{};
        
        final docDetails = projectData.documents[docType]?['details'] as List<dynamic>? ?? [];
        final projectBasePath = projectData.projectPath ?? '';

        for (var detail in docDetails) {
          final fileName = detail['name']?.toString() ?? '';
          final filePath = detail['full_path']?.toString() ?? '';
          if (fileName.isNotEmpty && !uniqueFiles.containsKey(fileName)) {
            uniqueFiles[fileName] = model.FileNode(
              name: fileName,
              path: filePath,
              isDirectory: false,
              children: [],
            );
          }
        }

        // exists가 true이고 파일이 없는 경우 기본 파일 추가
        if (uniqueFiles.isEmpty && projectData.documents[docType]?['exists'] == true) {
          final fileName = "${docType.toLowerCase()}_${projectId}.pdf";
          if (!uniqueFiles.containsKey(fileName)) {
            final fullPath = '$projectBasePath\\01. 행정\\01. 계약\\02.계약서\\$fileName';
            uniqueFiles[fileName] = model.FileNode(
              name: fileName,
              path: fullPath,
              isDirectory: false,
              children: [],
            );
          }
        }
        
        final result = uniqueFiles.values.toList()
          ..sort((a, b) => a.name.compareTo(b.name));  // 정렬 추가
        
        // 결과를 캐시에 저장
        _directoryCache[dirPath] = result;
        return result;
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

  String _getDocumentTypeName(String type) {
    switch (type) {
      case 'contract': return '계약서';
      case 'specification': return '과업지시서';
      case 'initiation': return '착수계';
      case 'agreement': return '업무협정';
      case 'budget': return '실행예산';
      case 'deliverable1': return '보고서';
      case 'deliverable2': return '도면';
      case 'completion': return '준공계';
      case 'certificate': return '실적증명';
      case 'evaluation': return '평가';
      default: return type;
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