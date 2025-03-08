// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;
import '../services/file_explorer_service.dart';
import '../widgets/tree_view.dart';

class FileExplorerScreen extends StatelessWidget {
  final String projectId;
  final Function(String)? onFileTap;

  const FileExplorerScreen({
    Key? key,
    required this.projectId,
    this.onFileTap,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        final node = service.rootNodes?.firstWhere(
          (n) => n.path == projectId,
          orElse: () => model.FileNode(name: '', path: '', isDirectory: true, children: []),
        );
        if (node == null || service.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (service.error != null) {
          return Center(child: Text('Error: ${service.error}'));
        }
        if (node.children.isEmpty) {
          return const Center(child: Text('No files available'));
        }
        return TreeView(
          nodes: node.children,
          onNodeTap: (node) {
            if (!node.isDirectory && onFileTap != null) {
              onFileTap!(node.path);
            }
          },
          onNodeExpand: (expandedNode) {
            if (!expandedNode.children.isEmpty) return;
            service.loadChildren(expandedNode);
          },
        );
      },
    );
  }
}