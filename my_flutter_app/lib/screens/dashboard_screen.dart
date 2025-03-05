// /lib/screens/dashboard_screen.dart

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/dashboard_bloc.dart';
import '../models/project_model.dart';
import '../models/department_summary.dart';
import '../services/api_service.dart';
import '../widgets/department_card.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (context) => DashboardBloc(
        apiService: ApiService(),
      )..add(LoadDashboardData()),
      child: const DashboardView(),
    );
  }
}

class DashboardView extends StatefulWidget {
  const DashboardView({super.key});

  @override
  State<DashboardView> createState() => _DashboardViewState();
}

class _DashboardViewState extends State<DashboardView> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('부서별 감사 결과 대시보드'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              context.read<DashboardBloc>().add(LoadDashboardData());
            },
          ),
        ],
      ),
      body: BlocBuilder<DashboardBloc, DashboardState>(
        builder: (context, state) {
          if (state is DashboardLoading) {
            return const Center(child: CircularProgressIndicator());
          } else if (state is DashboardLoaded) {
            return _buildDashboard(context, state.projects);
          } else if (state is DashboardError) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text('오류 발생: ${state.message}'),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () {
                      context.read<DashboardBloc>().add(LoadDashboardData());
                    },
                    child: const Text('재시도'),
                  ),
                ],
              ),
            );
          }
          return const Center(child: Text('데이터를 로드 중입니다...'));
        },
      ),
    );
  }

  Widget _buildDashboard(BuildContext context, List<ProjectModel> projects) {
    // 부서별로 프로젝트 그룹화
    final departments = <String, List<ProjectModel>>{};
    for (final project in projects) {
      departments.putIfAbsent(project.department, () => []).add(project);
    }

    // 부서별 요약 정보 계산
    final summaries = departments.map((department, projects) {
      final completedProjects = projects.where((p) => 
        p.status.toLowerCase() == '완료' || p.status.toLowerCase() == 'completed'
      ).length;

      return MapEntry(
        department,
        DepartmentSummary(
          totalProjects: projects.length,
          completedProjects: completedProjects,
          inProgressProjects: projects.length - completedProjects,
          contractExists: _countExistingDocs(projects, 'contract'),
          specificationExists: _countExistingDocs(projects, 'specification'),
          initiationExists: _countExistingDocs(projects, 'initiation'),
          agreementExists: _countExistingDocs(projects, 'agreement'),
          budgetExists: _countExistingDocs(projects, 'budget'),
          deliverable1Exists: _countExistingDocs(projects, 'deliverable1'),
          deliverable2Exists: _countExistingDocs(projects, 'deliverable2'),
          completionExists: _countExistingDocs(projects, 'completion'),
          certificateExists: _countExistingDocs(projects, 'certificate'),
          projects: projects,
        ),
      );
    });

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: summaries.length,
      itemBuilder: (context, index) {
        final department = summaries.keys.elementAt(index);
        final summary = summaries[department]!;

        return DepartmentCard(
          department: department,
          totalProjects: summary.totalProjects,
          completedProjects: summary.completedProjects,
          riskLevel: _calculateRiskLevel(summary),
          onTap: () => _showProjectDetails(context, summary.projects),
        );
      },
    );
  }

  int _countExistingDocs(List<ProjectModel> projects, String docType) {
    return projects.where((p) => 
      p.documents[docType]?['exists'] == true
    ).length;
  }

  int _calculateRiskLevel(DepartmentSummary summary) {
    // 문서 완성도를 기반으로 위험도 계산 (0~100)
    // 문서 완성도가 낮을수록 위험도가 높음
    return (100 - summary.documentCompletionRate).round();
  }

  void _showProjectDetails(BuildContext context, List<ProjectModel> projects) {
    showModalBottomSheet(
      context: context,
      builder: (context) {
        return ListView.builder(
          shrinkWrap: true,
          itemCount: projects.length,
          itemBuilder: (context, index) {
            final project = projects[index];
            return ListTile(
              title: Text('${project.projectId} - ${project.projectName}'),
              subtitle: Text('상태: ${project.status}'),
              onTap: () {
                Navigator.pop(context);
                _navigateToProjectDetails(context, project);
              },
            );
          },
        );
      },
    );
  }

  void _navigateToProjectDetails(BuildContext context, ProjectModel project) {
    Navigator.pushNamed(
      context,
      '/project_details',
      arguments: project,
    );
  }
} 