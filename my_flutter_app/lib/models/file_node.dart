// /my_flutter_app/lib/models/file_node.dart


class FileNode {
  final String name;
  final String path;
  final bool isDirectory;
  List<FileNode> children;
  bool isExpanded;

  FileNode({
    required this.name,
    required this.path,
    required this.isDirectory,
    this.children = const [],
    this.isExpanded = false,
  });

  factory FileNode.fromJson(Map<String, dynamic> json) {
    return FileNode(
      name: json['name'] as String,
      path: json['path'] as String,
      isDirectory: json['isDirectory'] as bool,
      children: (json['children'] as List<dynamic>?)
          ?.map((child) => FileNode.fromJson(child))
          .toList() ?? [],
      isExpanded: json['isExpanded'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'path': path,
      'isDirectory': isDirectory,
      'children': children.map((child) => child.toJson()).toList(),
      'isExpanded': isExpanded,
    };
  }
}