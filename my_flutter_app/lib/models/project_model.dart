// /lib/models/project_model.dart


import 'dart:convert';

/// 프로젝트 모델 클래스
class ProjectModel {
  /// 프로젝트 ID (null이면 'Unknown'로 기본값 설정)
  final String projectId;
  
  /// 프로젝트 이름 (null이면 'Unnamed Project'로 기본값 설정)
  final String projectName;
  
  /// 부서 (null이면 'Unknown Department'로 기본값 설정)
  final String department;
  
  /// 상태 (null이면 'Unknown Status'로 기본값 설정)
  final String status;
  
  /// 계약자 (null이면 'Unknown Contractor'로 기본값 설정)
  final String contractor;
  
  /// 문서 목록 (null이면 빈 맵으로 기본값 설정)
  final Map<String, Map<String, dynamic>> documents;
  
  /// AI 분석 결과 (null 허용)
  final String? aiAnalysis;
  
  /// 타임스탬프 (null이면 현재 시간으로 기본값 설정)
  final String timestamp;

  /// 생성자
  ProjectModel({
    required this.projectId,
    required this.projectName,
    required this.department,
    required this.status,
    required this.contractor,
    required this.documents,
    this.aiAnalysis,
    required this.timestamp,
  });

  /// JSON 데이터로부터 ProjectModel 생성
  factory ProjectModel.fromJson(Map<String, dynamic> json) {
    return ProjectModel(
      projectId: _parseString(json['project_id']) ?? 'Unknown',
      projectName: _parseString(json['project_name']) ?? 'Unnamed Project',
      department: _parseString(json['department']) ?? 'Unknown Department',
      status: _parseString(json['status']) ?? 'Unknown Status',
      contractor: _parseString(json['contractor']) ?? 'Unknown Contractor',
      documents: _parseDocuments(json['documents']) ?? {},
      aiAnalysis: json['ai_analysis'] as String?,
      timestamp: _parseString(json['timestamp']) ?? DateTime.now().toIso8601String(),
    );
  }

  /// JSON 데이터로 변환
  Map<String, dynamic> toJson() {
    return {
      'project_id': projectId,
      'project_name': projectName,
      'department': department,
      'status': status,
      'contractor': contractor,
      'documents': documents,
      'ai_analysis': aiAnalysis,
      'timestamp': timestamp,
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