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
    this.isDirectory = false,
    this.children = const [],
    this.isExpanded = false,
  });

  FileNode copyWith({
    String? name,
    String? path,
    bool? isDirectory,
    List<FileNode>? children,
    bool? isExpanded,
  }) {
    return FileNode(
      name: name ?? this.name,
      path: path ?? this.path,
      isDirectory: isDirectory ?? this.isDirectory,
      children: children ?? this.children,
      isExpanded: isExpanded ?? this.isExpanded,
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

  factory FileNode.fromJson(Map<String, dynamic> json) {
    return FileNode(
      name: json['name'] as String,
      path: json['path'] as String,
      isDirectory: json['isDirectory'] as bool,
      children: (json['children'] as List<dynamic>)
          .map((e) => FileNode.fromJson(e as Map<String, dynamic>))
          .toList(),
      isExpanded: json['isExpanded'] as bool,
    );
  }
} 