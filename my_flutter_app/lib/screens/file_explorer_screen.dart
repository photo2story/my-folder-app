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
            print('[DEBUG] onNodeTap triggered for node: ${node.path}, isDirectory: ${node.isDirectory}');
            final parts = node.path.split('/');
            print('[DEBUG] Node path parts: $parts');
            if (parts.length >= 2 && parts[1].isNotEmpty && node.isDirectory) {
              print('[DEBUG] Identified as project node');
              if (onProjectTap != null) {
                final projectId = parts[parts.length - 1];
                print('[DEBUG] Extracted projectId: $projectId');
                onProjectTap!(projectId);
              }
            } else if (!node.isDirectory && onFileTap != null) {
              print('[DEBUG] Identified as file node');
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