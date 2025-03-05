// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'package:flutter/material.dart';
import '../services/file_explorer_service.dart';

class FileExplorerScreen extends StatefulWidget {
  const FileExplorerScreen({super.key});

  @override
  State<FileExplorerScreen> createState() => _FileExplorerScreenState();
}

class _FileExplorerScreenState extends State<FileExplorerScreen> {
  final FileExplorerService _service = FileExplorerService();
  List<FileNode> _nodes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadInitialData();
  }

  Future<void> _loadInitialData() async {
    setState(() => _loading = true);
    try {
      final nodes = await _service.getDirectoryContents(FileExplorerService.networkDrivePath);
      setState(() {
        _nodes = nodes;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error loading directory: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('File Explorer'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadInitialData,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              itemCount: _nodes.length,
              itemBuilder: (context, index) {
                return _buildTreeNode(_nodes[index]);
              },
            ),
    );
  }

  Widget _buildTreeNode(FileNode node) {
    if (!node.isDirectory) {
      return ListTile(
        leading: const Icon(Icons.insert_drive_file),
        title: Text(node.label),
      );
    }

    return ExpansionTile(
      leading: const Icon(Icons.folder),
      title: Text(node.label),
      children: node.children.isEmpty
          ? [
              FutureBuilder<List<FileNode>>(
                future: _service.loadChildren(node.path),
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const ListTile(
                      title: Text('Loading...'),
                      leading: CircularProgressIndicator(),
                    );
                  }
                  if (snapshot.hasError) {
                    return ListTile(
                      title: Text('Error: ${snapshot.error}'),
                    );
                  }
                  if (snapshot.hasData) {
                    node.children = snapshot.data!;
                    return Column(
                      children: node.children.map(_buildTreeNode).toList(),
                    );
                  }
                  return const ListTile(title: Text('No children'));
                },
              ),
            ]
          : node.children.map(_buildTreeNode).toList(),
    );
  }
}