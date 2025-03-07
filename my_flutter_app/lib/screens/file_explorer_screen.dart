// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/file_explorer_service.dart';
import '../services/api_service.dart';
import '../models/project_model.dart';
import 'package:intl/intl.dart';

class FileExplorerScreen extends StatefulWidget {
  final String? initialProjectId;

  const FileExplorerScreen({Key? key, this.initialProjectId}) : super(key: key);

  @override
  _FileExplorerScreenState createState() => _FileExplorerScreenState();
}

class _FileExplorerScreenState extends State<FileExplorerScreen> {
  final ApiService _apiService = ApiService();
  List<FileNode> _nodes = [];
  Map<String, bool> _expandedNodes = {};

  @override
  void initState() {
    super.initState();
    _loadInitialData();
  }

  Future<void> _loadInitialData() async {
    try {
      final nodes = await _apiService.fetchDirectoryContents('');
      setState(() {
        _nodes = nodes;
      });
    } catch (e) {
      print('Error loading data: $e');
    }
  }

  Future<void> _loadChildren(FileNode node) async {
    if (!node.isDirectory) return;
    
    try {
      final children = await _apiService.fetchDirectoryContents(node.path);
      setState(() {
        node.children = children;
        _expandedNodes[node.path] = true;
      });
    } catch (e) {
      print('Error loading children: $e');
    }
  }

  Widget _buildTreeNode(FileNode node, int depth) {
    final isExpanded = _expandedNodes[node.path] ?? false;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () async {
            if (node.isDirectory) {
              if (!isExpanded) {
                await _loadChildren(node);
              } else {
                setState(() {
                  _expandedNodes[node.path] = false;
                });
              }
            }
          },
          child: Padding(
            padding: EdgeInsets.only(left: depth * 24.0, right: 8.0, top: 8.0, bottom: 8.0),
            child: Row(
              children: [
                if (node.isDirectory)
                  Icon(
                    isExpanded ? Icons.folder_open : Icons.folder,
                    color: Colors.blue,
                  )
                else
                  Icon(Icons.insert_drive_file, color: Colors.grey),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    node.name,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: depth == 0 ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (isExpanded && node.children.isNotEmpty)
          ...node.children.map((child) => _buildTreeNode(child, depth + 1)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('문서 탐색기'),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: _loadInitialData,
          ),
        ],
      ),
      body: _nodes.isEmpty
          ? Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: _nodes.map((node) => _buildTreeNode(node, 0)).toList(),
              ),
            ),
    );
  }
}