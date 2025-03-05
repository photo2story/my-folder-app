// /lib/models/department_summary.dart


import 'project_model.dart';

class DepartmentSummary {
  final int totalProjects;
  final int completedProjects;
  final int inProgressProjects;
  final int contractExists;
  final int specificationExists;
  final int initiationExists;
  final int agreementExists;
  final int budgetExists;
  final int deliverable1Exists;
  final int deliverable2Exists;
  final int completionExists;
  final int certificateExists;
  final List<ProjectModel> projects;

  DepartmentSummary({
    required this.totalProjects,
    required this.completedProjects,
    required this.inProgressProjects,
    required this.contractExists,
    required this.specificationExists,
    required this.initiationExists,
    required this.agreementExists,
    required this.budgetExists,
    required this.deliverable1Exists,
    required this.deliverable2Exists,
    required this.completionExists,
    required this.certificateExists,
    required this.projects,
  });

  double get documentCompletionRate {
    final totalDocs = 9; // 전체 문서 유형 수
    final existingDocs = [
      contractExists,
      specificationExists,
      initiationExists,
      agreementExists,
      budgetExists,
      deliverable1Exists,
      deliverable2Exists,
      completionExists,
      certificateExists,
    ].where((exists) => exists == 1).length;
    
    return (existingDocs / totalDocs * 100);
  }
} 