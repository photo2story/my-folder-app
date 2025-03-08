import 'package:flutter/material.dart';
import '../models/file_node.dart';

class TreeView extends StatefulWidget {
  final List<FileNode> nodes;
  final Function(FileNode)? onNodeTap;
  final Function(FileNode)? onNodeExpand;

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

  Widget _buildNode(FileNode node, int level) {
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
            } else {
              if (widget.onNodeTap != null) {
                widget.onNodeTap!(node);
              }
            }
          },
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
                    style: const TextStyle(fontSize: 14),
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