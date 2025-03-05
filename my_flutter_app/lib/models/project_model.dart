import 'dart:convert';

class ProjectModel {
  final String projectId;
  final String projectName;
  final String department;
  final String status;
  final String contractor;
  final Map<String, Map<String, dynamic>> documents;
  final String? aiAnalysis;
  final String timestamp;

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

  factory ProjectModel.fromJson(Map<String, dynamic> json) {
    return ProjectModel(
      projectId: json['project_id'] as String,
      projectName: json['project_name'] as String,
      department: json['department'] as String,
      status: json['status'] as String,
      contractor: json['contractor'] as String,
      documents: (json['documents'] as Map<String, dynamic>).map(
        (key, value) => MapEntry(key, Map<String, dynamic>.from(value)),
      ),
      aiAnalysis: json['ai_analysis'] as String?,
      timestamp: json['timestamp'] as String,
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
      'ai_analysis': aiAnalysis,
      'timestamp': timestamp,
    };
  }
} 