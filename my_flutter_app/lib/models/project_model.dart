// /lib/models/project_model.dart


import 'dart:convert';
import 'dart:math' as math;

/// 프로젝트 모델 클래스
class ProjectModel {
  final String projectId;
  final String projectName;
  final String department;
  final String status;
  final String contractor;
  final Map<String, dynamic> documents;
  final String timestamp;
  final String? aiAnalysis;
  final String? projectPath;

  ProjectModel({
    required this.projectId,
    required this.projectName,
    required this.department,
    required this.status,
    required this.contractor,
    required this.documents,
    required this.timestamp,
    this.aiAnalysis,
    this.projectPath,
  });

  factory ProjectModel.fromJson(Map<String, dynamic> json) {
    print('[DEBUG] Parsing JSON: ${json.keys}');
    Map<String, dynamic> parsedDocuments = {};
    if (json['documents'] != null && json['documents'] is Map) {
      parsedDocuments = Map<String, dynamic>.from(json['documents']);
    }

    // aiAnalysis 필드 처리 개선
    String? aiAnalysis;
    if (json['ai_analysis'] != null) {
      aiAnalysis = json['ai_analysis'].toString();
    } else if (json['aiAnalysis'] != null) {
      aiAnalysis = json['aiAnalysis'].toString();
    }
    
    if (aiAnalysis != null && aiAnalysis.isNotEmpty) {
      print('[DEBUG] AI Analysis from JSON: ${aiAnalysis.substring(0, math.min(50, aiAnalysis.length))}...');
    } else {
      print('[DEBUG] AI Analysis from JSON: null or empty');
    }

    return ProjectModel(
      projectId: json['project_id']?.toString() ?? '',
      projectName: json['project_name']?.toString() ?? '',
      department: json['department']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      contractor: json['contractor']?.toString() ?? '',
      documents: parsedDocuments,
      timestamp: json['timestamp']?.toString() ?? DateTime.now().toIso8601String(),
      aiAnalysis: aiAnalysis,
      projectPath: json['project_path']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'project_id': projectId,
      'project_name': projectName,
      'department': department,
      'status': status,
      'contractor': contractor,
      'documents': documents,
      'timestamp': timestamp,
      'ai_analysis': aiAnalysis,
      'project_path': projectPath,
    };
  }
}