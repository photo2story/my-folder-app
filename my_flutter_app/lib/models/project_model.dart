// /lib/models/project_model.dart


import 'dart:convert';

/// 프로젝트 모델 클래스
class ProjectModel {
  final String projectId;
  final String projectName;
  final String department;
  final String status;
  final String contractor;
  final Map<String, dynamic> documents;
  final String timestamp;
  final String? aiAnalysis; // AI 분석 보고서 필드 (JSON의 ai_analysis)
  final String? projectPath; // 네트워크 드라이브 경로

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
    // documents 파싱 로직 강화
    Map<String, dynamic> parsedDocuments = {};
    if (json['documents'] != null && json['documents'] is Map) {
      parsedDocuments = Map<String, dynamic>.from(json['documents']);
    }

    return ProjectModel(
      projectId: json['project_id']?.toString() ?? '',
      projectName: json['project_name']?.toString() ?? '',
      department: json['department']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      contractor: json['contractor']?.toString() ?? '',
      documents: parsedDocuments,
      timestamp: json['timestamp']?.toString() ?? DateTime.now().toIso8601String(),
      aiAnalysis: json['ai_analysis']?.toString(),
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


  /// String 또는 null을 안전하게 파싱
  static String? _parseString(dynamic value) {
    if (value == null) return null;
    return value is String ? value : value.toString();
  }

  /// 문서 맵을 안전하게 파싱
  static Map<String, Map<String, dynamic>>? _parseDocuments(dynamic value) {
    if (value == null) return null;
    if (value is! Map) return null;
    try {
      return (value as Map<String, dynamic>).map(
        (key, value) => MapEntry(key, Map<String, dynamic>.from(value)),
      );
    } catch (e) {
      return null;
    }
  }
} 