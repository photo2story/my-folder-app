// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;
import '../services/file_explorer_service.dart';
import '../widgets/tree_view.dart';

class FileExplorerScreen extends StatelessWidget {
  final String projectId;
  final Function(String)? onFileTap;
  final Function(String)? onProjectTap;

  const FileExplorerScreen({
    Key? key,
    required this.projectId,
    this.onFileTap,
    this.onProjectTap,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (service.isLoading) return const Center(child: CircularProgressIndicator());
        if (service.error != null) return Center(child: Text('Error: ${service.error}'));

        final rootNodes = service.rootNodes ?? [];
        if (rootNodes.isEmpty) return const Center(child: Text('부서가 없습니다'));

        return TreeView(
          nodes: rootNodes,
          onNodeTap: (node) async {
            print('[DEBUG] onNodeTap triggered for node: ${node.path}, isDirectory: ${node.isDirectory}, name: ${node.name}');
            final parts = node.path.split('/');
            print('[DEBUG] Node path parts: $parts');
            
            // 프로젝트 노드 식별 로직 개선
            if (node.isDirectory) {
              // 프로젝트 ID 추출 시도
              String? extractedProjectId;
              
              // 경로에서 추출 시도 (예: /10010_플랫폼사업실/A20230001)
              if (parts.length >= 3 && parts[0].isEmpty && parts[1].isNotEmpty && parts[2].isNotEmpty) {
                extractedProjectId = parts[2];
                print('[DEBUG] Extracted projectId from path: $extractedProjectId');
              }
              
              // 이름에서 추출 시도 (예: "A20230001 (프로젝트명 - 상태 - 계약자)")
              if (extractedProjectId == null && node.name.isNotEmpty) {
                final nameMatch = RegExp(r'^([A-Z]\d+)').firstMatch(node.name);
                if (nameMatch != null) {
                  extractedProjectId = nameMatch.group(1);
                  print('[DEBUG] Extracted projectId from name: $extractedProjectId');
                }
              }
              
              // 프로젝트 ID가 추출되었으면 콜백 호출
              if (extractedProjectId != null && onProjectTap != null) {
                print('[DEBUG] Calling onProjectTap with projectId: $extractedProjectId');
                onProjectTap!(extractedProjectId);
              } else {
                print('[DEBUG] Directory node but not a project or could not extract ID: ${node.path}');
              }
            } else if (!node.isDirectory && onFileTap != null) {
              print('[DEBUG] Identified as file node: ${node.path}');
              onFileTap!(node.path);
            }
          },
          onNodeExpand: (expandedNode) {
            if (!expandedNode.children.isEmpty) return;
            service.loadChildren(expandedNode).then((_) {
              print('[DEBUG] Expanded node ${expandedNode.path} loaded');
            }).catchError((e) {
              print('[ERROR] Failed to expand node: $e');
            });
          },
        );
      },
    );
  }
}