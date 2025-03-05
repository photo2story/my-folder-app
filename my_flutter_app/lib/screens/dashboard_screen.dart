import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/dashboard_bloc.dart';
import '../models/project_model.dart';
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
    // 부서별로 그룹화
    final departments = <String, List<ProjectModel>>{};
    for (final project in projects) {
      departments.putIfAbsent(project.department, () => []).add(project);
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: departments.length,
      itemBuilder: (context, index) {
        final department = departments.keys.elementAt(index);
        final projectsInDepartment = departments[department]!;
        final totalProjects = projectsInDepartment.length;
        final completedProjects = projectsInDepartment
            .where((p) => p.status.toLowerCase() == '완료')
            .length;
        final riskLevel = _calculateAverageRisk(projectsInDepartment);

        return DepartmentCard(
          department: department,
          totalProjects: totalProjects,
          completedProjects: completedProjects,
          riskLevel: riskLevel,
          onTap: () {
            _showProjectDetails(context, projectsInDepartment);
          },
        );
      },
    );
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
              subtitle: Text('상태: ${project.status}, 위험도: ${_calculateRisk(project)}%'),
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

  int _calculateAverageRisk(List<ProjectModel> projects) {
    if (projects.isEmpty) return 0;
    final totalRisk = projects.fold(0, (sum, project) => sum + _calculateRisk(project));
    return (totalRisk / projects.length).round();
  }

  int _calculateRisk(ProjectModel project) {
    // 문서 완성도를 기반으로 위험도 계산 (0~100)
    final totalDocs = project.documents.length;
    if (totalDocs == 0) return 0;
    
    final missingDocs = project.documents.values
        .where((doc) => !doc.containsKey('exists') || !doc['exists'] as bool)
        .length;
    return (missingDocs / totalDocs * 100).round();
  }
} 