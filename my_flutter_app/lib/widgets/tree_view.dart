// /my_flutter_app/lib/widgets/tree_view.dart 

import 'package:flutter/material.dart';
import '../models/file_node.dart' as model;

class TreeView extends StatefulWidget {
  final List<model.FileNode> nodes;
  final Function(model.FileNode)? onNodeTap;
  final Function(model.FileNode)? onNodeExpand;

  const TreeView({
    Key? key,
    required this.nodes,
    this.onNodeTap,
    this.onNodeExpand,
  }) : super(key: key);

  @override
  State<TreeView> createState() => _TreeViewState();
}

class _TreeViewState extends State<TreeView> {
  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: widget.nodes.length,
      itemBuilder: (context, index) {
        return _buildNode(widget.nodes[index], 0);
      },
    );
  }

  Widget _buildNode(model.FileNode node, int level) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            if (node.isDirectory) {
              setState(() {
                node.isExpanded = !node.isExpanded;
              });
              if (widget.onNodeExpand != null) {
                widget.onNodeExpand!(node);
              }
              if (widget.onNodeTap != null) {
                print('[DEBUG] Directory node tapped: ${node.path}');
                widget.onNodeTap!(node);
              }
            } else {
              if (widget.onNodeTap != null) {
                widget.onNodeTap!(node);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Opening ${node.name}...')),
                );
              }
            }
          },
          mouseCursor: SystemMouseCursors.click,
          hoverColor: Colors.grey[200],
          child: Padding(
            padding: EdgeInsets.only(left: level * 20.0, top: 8.0, bottom: 8.0),
            child: Row(
              children: [
                if (node.isDirectory)
                  Icon(
                    node.isExpanded ? Icons.folder_open : Icons.folder,
                    color: Colors.amber,
                  )
                else
                  const Icon(Icons.insert_drive_file, color: Colors.blue),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    node.name,
                    style: TextStyle(
                      fontSize: 14,
                      color: node.isDirectory ? Colors.black87 : Colors.blue,
                      fontWeight: node.isDirectory ? FontWeight.bold : FontWeight.normal,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (node.isDirectory && node.isExpanded)
          ...node.children.map((child) => _buildNode(child, level + 1)),
      ],
    );
  }
}