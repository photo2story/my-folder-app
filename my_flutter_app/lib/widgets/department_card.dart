import 'package:flutter/material.dart';

class DepartmentCard extends StatelessWidget {
  final String department;
  final int totalProjects;
  final int completedProjects;
  final int riskLevel;
  final VoidCallback onTap;

  const DepartmentCard({
    super.key,
    required this.department,
    required this.totalProjects,
    required this.completedProjects,
    required this.riskLevel,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final progress = (completedProjects / totalProjects * 100).round();
    final riskColor = riskLevel > 50 ? Colors.red : Colors.green;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 4,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                department,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text('총 프로젝트: $totalProjects건'),
              Text('완료된 프로젝트: $completedProjects건 (${progress}%)'),
              const SizedBox(height: 8),
              LinearProgressIndicator(
                value: completedProjects / totalProjects,
                backgroundColor: Colors.grey[200],
                valueColor: AlwaysStoppedAnimation<Color>(
                  progress > 70 ? Colors.green : Colors.orange,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('위험도: '),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: riskColor.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '$riskLevel%',
                      style: TextStyle(
                        color: riskColor,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
} 